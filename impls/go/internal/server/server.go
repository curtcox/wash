// Package server implements the wash HTTP server.
package server

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/curtcox/wash/impls/go/internal/executor"
	"github.com/curtcox/wash/impls/go/internal/filesystem"
	"github.com/curtcox/wash/impls/go/internal/metadata"
	"github.com/curtcox/wash/impls/go/internal/parser"
)

const maxErrorBody = 8192

// ServerConfig holds server-level state loaded at startup.
type ServerConfig struct {
	Root        string
	CommandDirs []string
	ExecConfig  executor.ExecConfig
}

// Server represents the wash HTTP server.
type Server struct {
	addr   string
	fs     *filesystem.FS
	config *ServerConfig
}

// New creates a new wash server instance.
func New(root, addr string) *Server {
	fs := filesystem.New(root)
	cmdDirs := loadCommandDirs(root, fs)
	execCfg := loadExecConfig(root)
	return &Server{
		addr: addr,
		fs:   fs,
		config: &ServerConfig{
			Root:        fs.Root(),
			CommandDirs: cmdDirs,
			ExecConfig:  execCfg,
		},
	}
}

// Start begins listening for HTTP requests.
func (s *Server) Start() error {
	return http.ListenAndServe(s.addr, http.HandlerFunc(s.dispatch))
}

func (s *Server) dispatch(w http.ResponseWriter, r *http.Request) {
	// RT-12.2: use raw request-target, never r.URL.Path
	rawTarget := r.RequestURI
	method := r.Method

	switch method {
	case http.MethodPut, http.MethodDelete:
		s.handleMutation(w, r, method, rawTarget)
		return
	case http.MethodOptions:
		w.Header().Set("Content-Length", "0")
		w.WriteHeader(http.StatusNoContent)
		return
	}

	var body []byte
	if method == http.MethodPost || method == http.MethodPatch {
		body = readBody(r)
	}

	result, err := parser.ParseRequest(
		method,
		rawTarget,
		s.config.Root,
		s.config.CommandDirs,
		true, // case_sensitive_lookup per capabilities
		"reject-escaping",
		s.fs,
		metadata.LoadMetadata,
	)
	if err != nil {
		pe, ok := err.(*parser.ParseError)
		if ok {
			s.sendError(w, r, pe.Status, pe.Message, nil)
		} else {
			s.sendError(w, r, http.StatusBadRequest, err.Error(), nil)
		}
		return
	}

	switch pr := result.(type) {
	case *parser.FilesystemParse:
		if method == http.MethodGet || method == http.MethodHead {
			s.handleFilesystemGet(w, r, pr.Resource)
			return
		}
		if method == http.MethodPost {
			s.sendError(w, r, http.StatusMethodNotAllowed, "POST not permitted for plain file resource", nil)
			return
		}
		s.sendError(w, r, http.StatusMethodNotAllowed, fmt.Sprintf("method %s not permitted", method), nil)
		return

	case *parser.NotFoundParse:
		s.sendError(w, r, http.StatusNotFound, "not found", nil)
		return

	case *parser.PipelineParse:
		s.handlePipeline(w, r, pr, body)
		return

	case *parser.RawCommandParse:
		s.handleRawCommand(w, r, pr, body)
		return
	}
}

func (s *Server) handleFilesystemGet(w http.ResponseWriter, r *http.Request, res *filesystem.Resource) {
	omitBody := r.Method == http.MethodHead
	var extraHeaders map[string]string
	if res.ViaIndirection {
		extraHeaders = map[string]string{"X-WebShell-Resolved-Path": res.Path}
	}

	if res.Kind == filesystem.KindFile {
		data, err := s.fs.ReadFile(res.Path)
		if err != nil {
			s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("read failed: %v", err), nil)
			return
		}
		ct, err := s.fs.InferMIMEType(res.Path)
		if err != nil {
			s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
			return
		}
		s.sendResponse(w, r, http.StatusOK, data, ct, extraHeaders, omitBody)
		return
	}

	// Directory: check for index file first (RT-6.5-dir-index, RT-7.5-env-index)
	indexNames, err := s.fs.LoadIndexNames()
	if err != nil {
		s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
		return
	}
	idx := s.fs.FindIndexFile(res.Path, indexNames)
	if idx != "" {
		data, err := s.fs.ReadFile(idx)
		if err != nil {
			s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("read index failed: %v", err), nil)
			return
		}
		ct, err := s.fs.InferMIMEType(idx)
		if err != nil {
			s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
			return
		}
		s.sendResponse(w, r, http.StatusOK, data, ct, extraHeaders, omitBody)
		return
	}

	enabled, err := s.fs.ListingEnabled()
	if err != nil {
		s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
		return
	}
	if !enabled {
		s.sendError(w, r, http.StatusNotFound, "not found", nil)
		return
	}

	listing, err := s.fs.DirectoryListing(res.Path)
	if err != nil {
		s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("listing failed: %v", err), nil)
		return
	}
	s.sendResponse(w, r, http.StatusOK, listing, "text/plain; charset=utf-8", extraHeaders, omitBody)
}

func (s *Server) handleMutation(w http.ResponseWriter, r *http.Request, method, rawTarget string) {
	rawSegs := filesystem.SplitRawTargetForMutation(rawTarget)
	parts, err := parser.LiteralPathPartsFromRaw(rawSegs)
	if err != nil {
		s.sendError(w, r, http.StatusBadRequest, "invalid path", nil)
		return
	}

	if method == http.MethodPut {
		body := readBody(r)
		resolved, resolveErr := s.fs.ResolveUnderRoot(parts, "reject-escaping", true)
		if resolveErr != nil {
			switch resolveErr.(type) {
			case *filesystem.NameEscapeError, *filesystem.EscapeError, *filesystem.SymlinkEscapeError:
				s.sendError(w, r, http.StatusForbidden, "path not permitted", nil)
			case *filesystem.NameLoopError:
				s.sendError(w, r, http.StatusLoopDetected, "name resolution loop detected", nil)
			default:
				s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("path resolution failed: %v", resolveErr), nil)
			}
			return
		}
		if resolved != "" {
			if info, statErr := os.Stat(resolved); statErr == nil && !info.IsDir() {
				literalTarget := filepath.Join(append([]string{s.config.Root}, filesystem.NormalizePathParts(parts)...)...)
				resolvedLiteral, literalErr := filepath.EvalSymlinks(literalTarget)
				if literalErr != nil {
					resolvedLiteral = filepath.Clean(literalTarget)
				}
				if filepath.Clean(resolved) != filepath.Clean(resolvedLiteral) {
					if err := os.WriteFile(resolved, body, 0o644); err != nil {
						s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("write failed: %v", err), nil)
						return
					}
					s.sendResponse(w, r, http.StatusOK, nil, "text/plain; charset=utf-8", nil, false)
					return
				}
			}
		}
		if putErr := s.fs.PutFile(parts, body, true, "reject-escaping"); putErr != nil {
			switch putErr.(type) {
			case *filesystem.EscapeError, *filesystem.SymlinkEscapeError:
				s.sendError(w, r, http.StatusForbidden, "path not permitted", nil)
			default:
				s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("write failed: %v", putErr), nil)
			}
			return
		}
		s.sendResponse(w, r, http.StatusOK, nil, "text/plain; charset=utf-8", nil, false)
		return
	}

	if method == http.MethodDelete {
		if delErr := s.fs.DeleteFile(parts, "reject-escaping"); delErr != nil {
			switch delErr.(type) {
			case *filesystem.EscapeError, *filesystem.SymlinkEscapeError, *filesystem.NameEscapeError:
				s.sendError(w, r, http.StatusForbidden, "path not permitted", nil)
				return
			case *filesystem.NameLoopError:
				s.sendError(w, r, http.StatusLoopDetected, "name resolution loop detected", nil)
				return
			}
			if strings.Contains(delErr.Error(), "not found") || strings.Contains(delErr.Error(), "no such file") {
				s.sendError(w, r, http.StatusNotFound, "file not found", nil)
				return
			}
			s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("delete failed: %v", delErr), nil)
			return
		}
		s.sendResponse(w, r, http.StatusOK, nil, "text/plain; charset=utf-8", nil, false)
		return
	}
}

func (s *Server) handlePipeline(w http.ResponseWriter, r *http.Request, p *parser.PipelineParse, body []byte) {
	method := r.Method

	// Check methods for all stages (HEAD treated as GET)
	if pe := parser.CheckMethods(p.Stages, method); pe != nil {
		s.sendError(w, r, pe.Status, pe.Message, nil)
		return
	}

	omitBody := method == http.MethodHead

	// Resolve input suffix bytes (implied cat)
	var stdinData []byte
	if len(p.InputSuffixRaw) > 0 {
		var err error
		stdinData, err = s.fs.ImpliedCatBytes(p.InputSuffixRaw, true, "reject-escaping")
		if err != nil {
			var notFoundErr *filesystem.NotFoundError
			var isDirErr *filesystem.IsDirError
			var nameEscapeErr *filesystem.NameEscapeError
			var escapeErr *filesystem.EscapeError
			var symlinkEscapeErr *filesystem.SymlinkEscapeError
			var nameLoopErr *filesystem.NameLoopError
			switch {
			case errors.As(err, &notFoundErr):
				s.sendError(w, r, http.StatusNotFound, err.Error(), nil)
			case errors.As(err, &isDirErr):
				s.sendError(w, r, http.StatusBadRequest, err.Error(), nil)
			case errors.As(err, &nameEscapeErr), errors.As(err, &escapeErr), errors.As(err, &symlinkEscapeErr):
				s.sendError(w, r, http.StatusForbidden, "path not permitted", nil)
			case errors.As(err, &nameLoopErr):
				s.sendError(w, r, http.StatusLoopDetected, "name resolution loop detected", nil)
			default:
				s.sendError(w, r, http.StatusInternalServerError, fmt.Sprintf("input suffix error: %v", err), nil)
			}
			return
		}
	}

	result, err := executor.ExecutePipeline(p, s.config.Root, s.config.CommandDirs, s.config.ExecConfig, body, stdinData)
	if err != nil {
		execErr, ok := err.(*executor.ExecutionError)
		if ok {
			s.sendError(w, r, execErr.Status, execErr.Message, nil)
		} else {
			s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
		}
		return
	}

	if result.HTTPStatus >= 400 {
		extra := map[string]interface{}{
			"pipeline": result.PipelineDescription,
		}
		if result.FailingStage != nil {
			extra["command"] = result.FailingStage.Name
			extra["exit_status"] = result.FailingStage.ExitCode
			if len(result.FailingStage.Stdout) > 0 {
				extra["stdout"] = truncate(string(result.FailingStage.Stdout), maxErrorBody)
			}
			if len(result.FailingStage.Stderr) > 0 {
				extra["stderr"] = truncate(string(result.FailingStage.Stderr), maxErrorBody)
			}
		}
		s.sendError(w, r, result.HTTPStatus, "command failed", extra)
		return
	}

	ct := filesystem.InferMIMEFromBytes(result.Stdout, result.ContentType)
	hdrs := pipelineHeaders(result)
	s.sendResponse(w, r, http.StatusOK, result.Stdout, ct, hdrs, omitBody)
}

func (s *Server) handleRawCommand(w http.ResponseWriter, r *http.Request, p *parser.RawCommandParse, body []byte) {
	method := r.Method
	if pe := parser.CheckMethods([]*parser.CommandStage{p.Stage}, method); pe != nil {
		s.sendError(w, r, pe.Status, pe.Message, nil)
		return
	}
	omitBody := method == http.MethodHead

	result, err := executor.ExecuteRawCommand(p, s.config.Root, s.config.CommandDirs, s.config.ExecConfig, body)
	if err != nil {
		execErr, ok := err.(*executor.ExecutionError)
		if ok {
			s.sendError(w, r, execErr.Status, execErr.Message, nil)
		} else {
			s.sendError(w, r, http.StatusInternalServerError, err.Error(), nil)
		}
		return
	}

	if result.HTTPStatus >= 400 {
		extra := map[string]interface{}{
			"pipeline": result.PipelineDescription,
		}
		if result.FailingStage != nil {
			extra["command"] = result.FailingStage.Name
			extra["exit_status"] = result.FailingStage.ExitCode
		}
		s.sendError(w, r, result.HTTPStatus, "command failed", extra)
		return
	}

	ct := filesystem.InferMIMEFromBytes(result.Stdout, result.ContentType)
	hdrs := pipelineHeaders(result)
	s.sendResponse(w, r, http.StatusOK, result.Stdout, ct, hdrs, omitBody)
}

func pipelineHeaders(result *executor.PipelineResult) map[string]string {
	hdrs := make(map[string]string)
	if result.FinalCommand != "" {
		hdrs["X-WebShell-Command"] = result.FinalCommand
	}
	if result.PipelineDescription != "" {
		hdrs["X-WebShell-Pipeline"] = result.PipelineDescription
	}
	if result.SourcePath != "" {
		hdrs["X-WebShell-Source"] = result.SourcePath
	}
	return hdrs
}

func (s *Server) sendResponse(w http.ResponseWriter, r *http.Request, status int, body []byte, ct string, hdrs map[string]string, omitBody bool) {
	w.Header().Set("Content-Type", ct)
	if omitBody {
		w.Header().Set("Content-Length", "0")
	} else {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(body)))
	}
	for k, v := range hdrs {
		w.Header().Set(k, v)
	}
	w.WriteHeader(status)
	if !omitBody && len(body) > 0 {
		w.Write(body)
	}
}

func (s *Server) sendError(w http.ResponseWriter, r *http.Request, status int, message string, extra map[string]interface{}) {
	body := buildErrorBody(r, status, message, extra)
	if len(body) > maxErrorBody {
		body = append(body[:maxErrorBody-32], []byte("\n... [truncated]\n")...)
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Length", fmt.Sprintf("%d", len(body)))
	w.WriteHeader(status)
	w.Write(body)
}

func buildErrorBody(r *http.Request, status int, message string, extra map[string]interface{}) []byte {
	if acceptsJSON(r) {
		payload := map[string]interface{}{
			"status": status,
			"error":  message,
		}
		for k, v := range extra {
			payload[k] = v
		}
		data, err := json.Marshal(payload)
		if err == nil {
			return append(data, '\n')
		}
	}
	var sb strings.Builder
	sb.WriteString(message)
	sb.WriteByte('\n')
	for k, v := range extra {
		sb.WriteString(fmt.Sprintf("%s: %v\n", k, v))
	}
	return []byte(sb.String())
}

func acceptsJSON(r *http.Request) bool {
	accept := r.Header.Get("Accept")
	if accept == "" {
		return false
	}
	parts := strings.Split(accept, ",")
	if len(parts) == 0 {
		return false
	}
	first := strings.TrimSpace(parts[0])
	return strings.Contains(accept, "application/json") && !strings.HasPrefix(first, "text/plain")
}

func readBody(r *http.Request) []byte {
	cl := r.ContentLength
	if cl <= 0 {
		return nil
	}
	buf := make([]byte, cl)
	n, _ := r.Body.Read(buf)
	return buf[:n]
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max]
}

// loadCommandDirs loads the command search path from env/path.
func loadCommandDirs(root string, fs *filesystem.FS) []string {
	envPathFile := root + "/env/path"
	data, err := fs.ReadFile(envPathFile)
	if err != nil {
		return nil
	}
	var dirs []string
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// Paths relative to root
		if !strings.HasPrefix(line, "/") {
			line = root + "/" + line
		}
		dirs = append(dirs, line)
	}
	return dirs
}

// loadExecConfig loads interpreter rules from the exec file.
func loadExecConfig(root string) executor.ExecConfig {
	data, err := readFile(root + "/exec")
	if err != nil {
		return executor.ExecConfig{}
	}
	var rules []executor.ExecRule
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) < 2 {
			return executor.ExecConfig{
				Rules:           rules,
				Malformed:       true,
				MalformedReason: fmt.Sprintf("malformed exec rule: %q", line),
			}
		}
		rules = append(rules, executor.ExecRule{
			Pattern:     parts[0],
			Interpreter: parts[1],
			ExtraArgs:   parts[2:],
		})
	}
	return executor.ExecConfig{Rules: rules}
}

func readFile(path string) ([]byte, error) {
	return os.ReadFile(path)
}
