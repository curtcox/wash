// Package parser implements URL pipeline parsing per pipeline_parsing.md.
package parser

import (
	"fmt"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/curtcox/wash/impls/go/internal/filesystem"
	"github.com/curtcox/wash/impls/go/internal/metadata"
)

// ParseError is returned when parsing fails.
type ParseError struct {
	Message string
	Status  int // HTTP status (400, 500, etc.)
}

func (e *ParseError) Error() string { return e.Message }

func parseErr(msg string) *ParseError  { return &ParseError{Message: msg, Status: 400} }
func serverErr(msg string) *ParseError { return &ParseError{Message: msg, Status: 500} }

// ParsedSegment is the result of parsing a single raw URL segment.
type ParsedSegment struct {
	Raw         string
	Name        string
	QueryItems  []QueryItem
	StderrMerge bool
}

// QueryItem holds a key=value pair from a per-command query string.
type QueryItem struct {
	Key   string
	Value string
}

// CommandStage is a single resolved command in a pipeline.
type CommandStage struct {
	Name                string
	CommandPath         string
	Argv                []string
	Meta                *metadata.CommandMetadata
	StderrMergeBoundary bool
	RawSegment          string
	ArgvFromQuery       bool
}

// PipelineParse is a successfully parsed command pipeline.
type PipelineParse struct {
	Stages              []*CommandStage
	InputSuffixRaw      []string // nil means no input suffix
	PipelineDescription string
	SourcePath          string
}

// RawCommandParse is a parse-mode raw command result.
type RawCommandParse struct {
	Stage     *CommandStage
	RawSuffix string
}

// FilesystemParse means the URL resolved to an exact filesystem resource.
type FilesystemParse struct {
	Resource *filesystem.Resource
}

// NotFoundParse means no resource or command parse was found.
type NotFoundParse struct{}

// ParseResult is the discriminated union returned by ParseRequest.
type ParseResult interface {
	parseResult()
}

func (*PipelineParse) parseResult()   {}
func (*RawCommandParse) parseResult() {}
func (*FilesystemParse) parseResult() {}
func (*NotFoundParse) parseResult()   {}

// SplitRawTarget splits the raw request-target on raw '/' before percent-decoding.
// Collapses empty segments (multiple slashes). Strips fragment.
func SplitRawTarget(rawTarget string) []string {
	// Strip fragment
	if idx := strings.IndexByte(rawTarget, '#'); idx != -1 {
		rawTarget = rawTarget[:idx]
	}
	if !strings.HasPrefix(rawTarget, "/") {
		rawTarget = "/" + rawTarget
	}
	parts := strings.Split(rawTarget, "/")
	var segments []string
	for _, p := range parts {
		if p == "" {
			continue
		}
		segments = append(segments, p)
	}
	return segments
}

// PercentDecodeSegment decodes a single URL segment.
// If forFilesystem is true, decoded '/' or NUL are rejected.
func PercentDecodeSegment(raw string, forFilesystem bool) (string, error) {
	decoded, err := url.PathUnescape(raw)
	if err != nil {
		return "", fmt.Errorf("invalid percent-encoding in %q: %w", raw, err)
	}
	if forFilesystem && (strings.Contains(decoded, "/") || strings.Contains(decoded, "\x00")) {
		return "", fmt.Errorf("decoded / or NUL in filesystem path segment: %q", raw)
	}
	return decoded, nil
}

// ParseSegment parses a single raw URL segment into its components.
func ParseSegment(raw string) *ParsedSegment {
	stderrMerge := false
	body := raw
	if strings.HasPrefix(body, "&") {
		stderrMerge = true
		body = body[1:]
	}

	var namePart, queryPart string
	if idx := strings.IndexByte(body, '?'); idx != -1 {
		namePart = body[:idx]
		queryPart = body[idx+1:]
	} else {
		namePart = body
	}

	name, _ := PercentDecodeSegment(namePart, false)

	var queryItems []QueryItem
	if queryPart != "" {
		for _, kv := range strings.Split(queryPart, "&") {
			if kv == "" {
				continue
			}
			eqIdx := strings.IndexByte(kv, '=')
			var k, v string
			if eqIdx == -1 {
				k = kv
			} else {
				k = kv[:eqIdx]
				v = kv[eqIdx+1:]
			}
			kDec, _ := url.QueryUnescape(k)
			vDec, _ := url.QueryUnescape(v)
			queryItems = append(queryItems, QueryItem{Key: kDec, Value: vDec})
		}
	}

	return &ParsedSegment{
		Raw:         raw,
		Name:        name,
		QueryItems:  queryItems,
		StderrMerge: stderrMerge,
	}
}

// coreArgvFromQuery extracts "arg" query values (core argv) from a segment's query items.
// Returns nil if no "arg" key is present.
func coreArgvFromQuery(items []QueryItem) []string {
	hasArg := false
	var args []string
	for _, item := range items {
		if item.Key == "arg" {
			hasArg = true
			args = append(args, item.Value)
		}
	}
	if !hasArg {
		return nil
	}
	return args
}

// ResolveCommand looks for 'name' in command dirs. Returns full path or "".
func ResolveCommand(name string, commandDirs []string, caseSensitive bool) string {
	for _, dir := range commandDirs {
		candidate := filepath.Join(dir, name)
		if fileExists(candidate) {
			return candidate
		}
		if !caseSensitive {
			entries, err := listDir(dir)
			if err != nil {
				continue
			}
			nameLower := strings.ToLower(name)
			for _, entry := range entries {
				if strings.ToLower(entry) == nameLower {
					p := filepath.Join(dir, entry)
					if fileExists(p) {
						return p
					}
				}
			}
		}
	}
	return ""
}

func fileExists(p string) bool {
	info, err := os.Stat(p)
	return err == nil && !info.IsDir()
}

func listDir(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		names = append(names, e.Name())
	}
	return names, nil
}

// remainingRawSuffix joins segments from start index with '/'.
func remainingRawSuffix(segments []string, start int) string {
	if start >= len(segments) {
		return ""
	}
	return strings.Join(segments[start:], "/")
}

func formatPipeline(stages []*CommandStage, inputSuffix []string) string {
	var parts []string
	if len(inputSuffix) > 0 {
		parts = append(parts, "cat "+strings.Join(inputSuffix, "/"))
	}
	for i := len(stages) - 1; i >= 0; i-- {
		stage := stages[i]
		cmd := stage.Name
		if len(stage.Argv) > 0 {
			cmd += " " + strings.Join(stage.Argv, " ")
		}
		parts = append(parts, cmd)
	}
	return strings.Join(parts, " | ")
}

// ParseRequest parses the raw request-target into a ParseResult.
// This implements the normative parse algorithm from pipeline_parsing.md §2.
func ParseRequest(
	method string,
	rawTarget string,
	root string,
	commandDirs []string,
	caseSensitive bool,
	symlinkPolicy string,
	fs *filesystem.FS,
	loadMeta func(root, name string) *metadata.CommandMetadata,
) (ParseResult, error) {
	// Strip fragment
	rawTarget = strings.SplitN(rawTarget, "#", 2)[0]

	segments := SplitRawTarget(rawTarget)

	// RT-12.2-root-escape / PP-9.1-invalid-segment: reject .. segments before any decoding
	for _, seg := range segments {
		name := seg
		if idx := strings.IndexByte(name, '?'); idx != -1 {
			name = name[:idx]
		}
		if name == ".." || name == "%2e%2e" || name == "%2E%2E" || name == "%2e." || name == ".%2e" || name == ".%2E" || name == "%2E." {
			return nil, &ParseError{Message: "path escapes root", Status: 400}
		}
		// Also check decoded value
		decoded, decErr := url.PathUnescape(name)
		if decErr == nil && decoded == ".." {
			return nil, &ParseError{Message: "path escapes root", Status: 400}
		}
	}

	// Step 2: Check exact filesystem resource first.
	res, err := fs.TryExactFilesystem(segments, caseSensitive, symlinkPolicy)
	if err != nil {
		return nil, parseErr(fmt.Sprintf("path error: %v", err))
	}
	if res != nil {
		return &FilesystemParse{Resource: res}, nil
	}

	// No exact filesystem resource — attempt command parsing.
	if len(segments) == 0 {
		return &NotFoundParse{}, nil
	}

	firstSeg := ParseSegment(segments[0])
	firstCmdPath := ResolveCommand(firstSeg.Name, commandDirs, caseSensitive)
	if firstCmdPath == "" {
		return &NotFoundParse{}, nil
	}

	var stages []*CommandStage
	idx := 0

	for idx < len(segments) {
		seg := ParseSegment(segments[idx])
		cmdPath := ResolveCommand(seg.Name, commandDirs, caseSensitive)
		if cmdPath == "" {
			if len(stages) == 0 {
				return &NotFoundParse{}, nil
			}
			break
		}

		meta := loadMeta(root, seg.Name)
		if meta.Malformed {
			return nil, serverErr(fmt.Sprintf("malformed metadata for command %s: %s", seg.Name, meta.MalformedReason))
		}

		if meta.ParseMode == "raw" {
			if len(stages) > 0 {
				return nil, serverErr(fmt.Sprintf("parse-mode raw on %s is only valid in leftmost position", seg.Name))
			}
			rawSuffix := remainingRawSuffix(segments, idx+1)
			stage := &CommandStage{
				Name:                seg.Name,
				CommandPath:         cmdPath,
				Argv:                nil,
				Meta:                meta,
				StderrMergeBoundary: seg.StderrMerge,
				RawSegment:          seg.Raw,
			}
			return &RawCommandParse{Stage: stage, RawSuffix: rawSuffix}, nil
		}

		queryArgv := coreArgvFromQuery(seg.QueryItems)
		argvFromQuery := queryArgv != nil
		var argv []string

		if queryArgv != nil {
			argv = queryArgv
			idx++
		} else if meta.Arity == "*" {
			// Consume all remaining segments as argv
			for _, s := range segments[idx+1:] {
				decoded, _ := PercentDecodeSegment(s, false)
				argv = append(argv, decoded)
			}
			idx = len(segments)
			stages = append(stages, &CommandStage{
				Name:                seg.Name,
				CommandPath:         cmdPath,
				Argv:                argv,
				Meta:                meta,
				StderrMergeBoundary: seg.StderrMerge,
				RawSegment:          seg.Raw,
				ArgvFromQuery:       argvFromQuery,
			})
			return &PipelineParse{
				Stages:              stages,
				InputSuffixRaw:      nil,
				PipelineDescription: formatPipeline(stages, nil),
			}, nil
		} else {
			// Fixed arity
			arityN := 0
			if n, ok := meta.Arity.(int); ok {
				arityN = n
			}
			if arityN > 0 && idx+arityN >= len(segments) {
				return nil, parseErr(fmt.Sprintf("command %s expects arity %d but insufficient path segments", seg.Name, arityN))
			}
			argv = make([]string, 0, arityN)
			for offset := 1; offset <= arityN; offset++ {
				argSeg := ParseSegment(segments[idx+offset])
				// Per PP-6.3-arg-noncmd-400: core arg on non-command segment -> 400
				if hasArgKey(argSeg.QueryItems) {
					if ResolveCommand(argSeg.Name, commandDirs, caseSensitive) == "" {
						return nil, parseErr(fmt.Sprintf("core arg query on non-command segment %q", argSeg.Name))
					}
				}
				decoded, _ := PercentDecodeSegment(segments[idx+offset], false)
				argv = append(argv, decoded)
			}
			idx += 1 + arityN
		}

		stages = append(stages, &CommandStage{
			Name:                seg.Name,
			CommandPath:         cmdPath,
			Argv:                argv,
			Meta:                meta,
			StderrMergeBoundary: seg.StderrMerge,
			RawSegment:          seg.Raw,
			ArgvFromQuery:       argvFromQuery,
		})

		if idx >= len(segments) {
			break
		}

		nextSeg := ParseSegment(segments[idx])
		if ResolveCommand(nextSeg.Name, commandDirs, caseSensitive) != "" {
			continue
		}

		// Next segment is not a command — check for invalid arg query
		if hasArgKey(nextSeg.QueryItems) {
			return nil, parseErr(fmt.Sprintf("core arg query on non-command segment %q", nextSeg.Name))
		}

		// Check that no later segment is a command (PP-7-mid-noncmd-400)
		remaining := segments[idx:]
		for _, later := range remaining[1:] {
			laterSeg := ParseSegment(later)
			if ResolveCommand(laterSeg.Name, commandDirs, caseSensitive) != "" {
				return nil, parseErr(fmt.Sprintf("unexpected segment %q before command %q", nextSeg.Name, laterSeg.Name))
			}
			if hasArgKey(laterSeg.QueryItems) {
				return nil, parseErr(fmt.Sprintf("core arg query on non-command segment %q", laterSeg.Name))
			}
		}

		// PP-13.1-mf-path-args / PP-13.2-mf-multi-path-args:
		// metadata-free command (arity 0, no query argv) can't have multi-segment suffix
		if len(remaining) > 1 {
			lastStage := stages[len(stages)-1]
			if !lastStage.ArgvFromQuery && lastStage.Meta.Arity == 0 && lastStage.Meta.ParseMode == "normal" {
				return nil, parseErr(fmt.Sprintf("metadata-free command %s cannot consume path argument segments", lastStage.Name))
			}
		}

		break
	}

	var inputSuffix []string
	if idx < len(segments) {
		inputSuffix = segments[idx:]
	}

	if len(stages) == 0 {
		return &NotFoundParse{}, nil
	}

	return &PipelineParse{
		Stages:              stages,
		InputSuffixRaw:      inputSuffix,
		PipelineDescription: formatPipeline(stages, inputSuffix),
		SourcePath:          joinSuffix(inputSuffix),
	}, nil
}

func joinSuffix(parts []string) string {
	if len(parts) == 0 {
		return ""
	}
	return path.Join(parts...)
}

func hasArgKey(items []QueryItem) bool {
	for _, item := range items {
		if item.Key == "arg" {
			return true
		}
	}
	return false
}

// CheckMethods verifies all stages permit the given HTTP method.
// HEAD is treated as GET for method checking.
func CheckMethods(stages []*CommandStage, method string) *ParseError {
	effective := method
	if method == "HEAD" {
		effective = "GET"
	}
	for _, stage := range stages {
		if len(stage.Meta.Methods) == 0 {
			if effective != "GET" {
				return &ParseError{
					Message: fmt.Sprintf("method %s not permitted by command %s", method, stage.Name),
					Status:  405,
				}
			}
			continue
		}
		found := false
		for _, m := range stage.Meta.Methods {
			if m == effective {
				found = true
				break
			}
		}
		if !found {
			return &ParseError{
				Message: fmt.Sprintf("method %s not permitted by command %s", method, stage.Name),
				Status:  405,
			}
		}
	}
	return nil
}

// LiteralPathPartsFromRaw decodes raw segments for filesystem use (PUT/DELETE).
func LiteralPathPartsFromRaw(segments []string) ([]string, error) {
	parts := make([]string, 0, len(segments))
	for _, seg := range segments {
		decoded, err := PercentDecodeSegment(seg, true)
		if err != nil {
			return nil, err
		}
		parts = append(parts, decoded)
	}
	return parts, nil
}
