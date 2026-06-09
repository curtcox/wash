package filesystem

import (
	"fmt"
	"mime"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// ResourceType indicates the type of filesystem resource
type ResourceType int

const (
	TypeNotFound ResourceType = iota
	TypeFile
	TypeDir
)

// Resource represents a resolved filesystem resource
type Resource struct {
	Type     ResourceType
	Path     string // Absolute filesystem path
	URLPath  string // URL path (decoded)
	MIMEType string
}

// DirEntry represents a single directory entry
type DirEntry struct {
	Name  string
	IsDir bool
}

// DirListing represents a directory's contents
type DirListing struct {
	Entries []DirEntry
}

// FS provides filesystem operations within a root directory
type FS struct {
	root string
}

// New creates a new filesystem handler for the given root
func New(root string) *FS {
	return &FS{root: root}
}

// ResolveExact resolves a URL path to an exact filesystem resource
// Implements RT-6.1-literal-file: Plain URL path maps literally to root file
func (fs *FS) ResolveExact(rawPath string) (*Resource, error) {
	// Clean the path - remove query string, fragment
	path := rawPath
	if idx := strings.IndexAny(path, "?#"); idx != -1 {
		path = path[:idx]
	}

	// Percent-decode the path
	decoded, err := decodePath(path)
	if err != nil {
		return nil, fmt.Errorf("invalid encoding: %w", err)
	}

	// Check for invalid characters (NUL is never allowed)
	// Per PP-9.1-invalid-segment: decoded / in segment content is invalid
	if strings.Contains(decoded, "\x00") {
		return nil, fmt.Errorf("invalid path characters: NUL")
	}

	// Per PP-9.1-slash-collapse: collapse multiple slashes
	// Per PP-9.1-invalid-segment: reject decoded / in segment content
	segments := splitPath(decoded)
	for _, seg := range segments {
		if strings.Contains(seg, "/") {
			return nil, fmt.Errorf("invalid segment: contains decoded slash")
		}
	}

	// Rebuild path with single separators
	cleanPath := strings.Join(segments, "/")

	// Strip leading slash for filesystem lookup (it's the root)
	cleanPath = strings.TrimPrefix(cleanPath, "/")

	// Check for root escape attempts (.. segments)
	// Per RT-12.2-root-escape: reject paths that escape root
	if containsDotDot(segments) {
		return nil, fmt.Errorf("path escapes root directory")
	}

	// Join with root and clean
	fullPath := filepath.Join(fs.root, filepath.Clean("/"+cleanPath))

	// RT-12.2-root-escape: Check for root escape
	if err := fs.checkEscape(fullPath); err != nil {
		return nil, err
	}

	// Stat the path
	info, err := os.Stat(fullPath)
	if err != nil {
		if os.IsNotExist(err) {
			return &Resource{Type: TypeNotFound}, nil
		}
		return nil, err
	}

	res := &Resource{
		Path:    fullPath,
		URLPath: decoded,
	}

	if info.IsDir() {
		res.Type = TypeDir
		res.MIMEType = "text/html; charset=utf-8"
	} else {
		res.Type = TypeFile
		res.MIMEType = inferMIMEType(fullPath)
	}

	return res, nil
}

// ReadFile reads the contents of a file
func (fs *FS) ReadFile(path string) ([]byte, error) {
	return os.ReadFile(path)
}

// ListDir returns a directory listing
func (fs *FS) ListDir(path string) (*DirListing, error) {
	entries, err := os.ReadDir(path)
	if err != nil {
		return nil, err
	}

	listing := &DirListing{
		Entries: make([]DirEntry, 0, len(entries)),
	}

	for _, entry := range entries {
		listing.Entries = append(listing.Entries, DirEntry{
			Name:  entry.Name(),
			IsDir: entry.IsDir(),
		})
	}

	return listing, nil
}

// checkEscape verifies the path does not escape the root directory
func (fs *FS) checkEscape(fullPath string) error {
	// Resolve any symlinks and get absolute path
	realPath, err := filepath.EvalSymlinks(fullPath)
	if err != nil {
		// If the path doesn't exist yet, check its parent
		if os.IsNotExist(err) {
			return fs.checkParentEscape(fullPath)
		}
		return err
	}

	realRoot, err := filepath.EvalSymlinks(fs.root)
	if err != nil {
		return err
	}

	// Ensure realPath has realRoot as prefix
	if !strings.HasPrefix(realPath, realRoot) {
		return fmt.Errorf("path escapes root directory")
	}

	return nil
}

func (fs *FS) checkParentEscape(fullPath string) error {
	// For non-existent paths, check the parent directory
	dir := filepath.Dir(fullPath)
	realDir, err := filepath.EvalSymlinks(dir)
	if err != nil {
		return err
	}

	realRoot, err := filepath.EvalSymlinks(fs.root)
	if err != nil {
		return err
	}

	if !strings.HasPrefix(realDir, realRoot) {
		return fmt.Errorf("path escapes root directory")
	}

	return nil
}

// decodePath percent-decodes a URL path
func decodePath(path string) (string, error) {
	// Use net/url's PathUnescape for percent decoding
	decoded, err := url.PathUnescape(path)
	if err != nil {
		return "", err
	}
	return decoded, nil
}

// splitPath splits a path on /, collapsing empty segments (multiple slashes)
func splitPath(path string) []string {
	var result []string
	segments := strings.Split(path, "/")
	for _, seg := range segments {
		if seg != "" {
			result = append(result, seg)
		}
	}
	return result
}

// containsDotDot returns true if any segment is exactly ".."
func containsDotDot(segments []string) bool {
	for _, seg := range segments {
		if seg == ".." {
			return true
		}
	}
	return false
}

// inferMIMEType determines the MIME type from file extension
func inferMIMEType(path string) string {
	ext := filepath.Ext(path)
	if ext == "" {
		return "application/octet-stream"
	}

	// Known mappings from capabilities
	mimeMap := map[string]string{
		".txt":  "text/plain",
		".json": "application/json",
		".html": "text/html",
		".htm":  "text/html",
		".css":  "text/css",
		".js":   "application/javascript",
		".png":  "image/png",
		".jpg":  "image/jpeg",
		".jpeg": "image/jpeg",
		".gif":  "image/gif",
		".svg":  "image/svg+xml",
		".xml":  "application/xml",
		".pdf":  "application/pdf",
	}

	if mimeType, ok := mimeMap[ext]; ok {
		return mimeType
	}

	// Fall back to mime.TypeByExtension
	if mimeType := mime.TypeByExtension(ext); mimeType != "" {
		return mimeType
	}

	return "application/octet-stream"
}
