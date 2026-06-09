package server

import (
	"fmt"
	"net/http"

	"github.com/curtcox/wash/impls/go/internal/filesystem"
)

// Server represents the wash HTTP server
type Server struct {
	root string
	addr string
	fs   *filesystem.FS
}

// New creates a new wash server instance
func New(root, addr string) *Server {
	return &Server{
		root: root,
		addr: addr,
		fs:   filesystem.New(root),
	}
}

// Start begins listening for HTTP requests
func (s *Server) Start() error {
	// Use a raw handler instead of ServeMux to avoid automatic redirects
	// for paths with multiple slashes or dot segments (per RT-12.2)
	return http.ListenAndServe(s.addr, http.HandlerFunc(s.handleRequest))
}

func (s *Server) handleRequest(w http.ResponseWriter, r *http.Request) {
	// Use r.RequestURI (raw) instead of r.URL.Path (cleaned) per spec RT-12.2
	rawTarget := r.RequestURI

	// For now, handle only GET for literal files (Phase 1)
	if r.Method != http.MethodGet {
		s.writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Resolve the raw target to a filesystem path
	resolved, err := s.fs.ResolveExact(rawTarget)
	if err != nil {
		s.writeError(w, http.StatusNotFound, "Not found")
		return
	}

	// Handle the resolved resource
	s.serveResource(w, r, resolved)
}

func (s *Server) serveResource(w http.ResponseWriter, r *http.Request, res *filesystem.Resource) {
	switch res.Type {
	case filesystem.TypeFile:
		s.serveFile(w, r, res)
	case filesystem.TypeDir:
		s.serveDir(w, r, res)
	default:
		s.writeError(w, http.StatusNotFound, "Not found")
	}
}

func (s *Server) serveFile(w http.ResponseWriter, r *http.Request, res *filesystem.Resource) {
	data, err := s.fs.ReadFile(res.Path)
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "Error reading file")
		return
	}

	w.Header().Set("Content-Type", res.MIMEType)
	w.WriteHeader(http.StatusOK)
	w.Write(data)
}

func (s *Server) serveDir(w http.ResponseWriter, r *http.Request, res *filesystem.Resource) {
	// For Phase 1: simple directory listing
	listing, err := s.fs.ListDir(res.Path)
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "Error listing directory")
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)

	fmt.Fprintf(w, "<html><body><h1>Directory: %s</h1><ul>", r.URL.Path)
	for _, entry := range listing.Entries {
		name := entry.Name
		if entry.IsDir {
			name += "/"
		}
		fmt.Fprintf(w, "<li><a href=\"%s\">%s</a></li>", name, name)
	}
	fmt.Fprint(w, "</ul></body></html>")
}

func (s *Server) writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(status)
	fmt.Fprintf(w, "%d %s\n%s\n", status, http.StatusText(status), message)
}
