package filesystem

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Built-in fallback MIME table per runtime.md §7.4.
var fallbackMIMETable = map[string]string{
	".html": "text/html",
	".htm":  "text/html",
	".txt":  "text/plain",
	".md":   "text/markdown",
	".json": "application/json",
	".css":  "text/css",
	".js":   "text/javascript",
	".mjs":  "text/javascript",
	".svg":  "image/svg+xml",
	".xml":  "application/xml",
	".png":  "image/png",
	".jpg":  "image/jpeg",
	".jpeg": "image/jpeg",
	".gif":  "image/gif",
	".webp": "image/webp",
	".ico":  "image/x-icon",
	".pdf":  "application/pdf",
	".wasm": "application/wasm",
}

const mimeDefault = "application/octet-stream"

// DefaultIndexNames applies when root/env/index is absent (runtime.md §7.5).
var DefaultIndexNames = []string{"index.html"}

// EnvConfigError is returned for a malformed root/env serving-config file.
type EnvConfigError struct{ msg string }

func (e *EnvConfigError) Error() string { return e.msg }

func envConfigLines(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var lines []string
	for _, raw := range strings.Split(string(data), "\n") {
		stripped := strings.TrimSpace(raw)
		if stripped == "" || strings.HasPrefix(stripped, "#") {
			continue
		}
		lines = append(lines, stripped)
	}
	return lines, nil
}

// LoadMIMEConfig parses root/env/mime per runtime.md §7.4.
// Returns (suffix map, declared default or "").
func (fs *FS) LoadMIMEConfig() (map[string]string, string, error) {
	mimeFile := filepath.Join(fs.root, "env", "mime")
	mapping := map[string]string{}
	if _, err := os.Stat(mimeFile); err != nil {
		return mapping, "", nil
	}
	lines, err := envConfigLines(mimeFile)
	if err != nil {
		return nil, "", err
	}
	declaredDefault := ""
	for _, line := range lines {
		tokens := strings.Fields(line)
		if len(tokens) != 2 {
			return nil, "", &EnvConfigError{fmt.Sprintf("malformed env/mime line: %q", line)}
		}
		key, mediaType := tokens[0], tokens[1]
		if !strings.Contains(mediaType, "/") {
			return nil, "", &EnvConfigError{fmt.Sprintf("malformed env/mime media type: %q", mediaType)}
		}
		switch {
		case key == "default":
			declaredDefault = mediaType
		case strings.HasPrefix(key, ".") && len(key) > 1:
			mapping[strings.ToLower(key)] = mediaType
		default:
			return nil, "", &EnvConfigError{fmt.Sprintf("malformed env/mime suffix: %q", key)}
		}
	}
	return mapping, declaredDefault, nil
}

// LoadIndexNames parses root/env/index per runtime.md §7.5.
func (fs *FS) LoadIndexNames() ([]string, error) {
	indexFile := filepath.Join(fs.root, "env", "index")
	if _, err := os.Stat(indexFile); err != nil {
		return append([]string{}, DefaultIndexNames...), nil
	}
	lines, err := envConfigLines(indexFile)
	if err != nil {
		return nil, err
	}
	names := []string{}
	for _, line := range lines {
		if strings.ContainsAny(line, "/\\\x00") || line == "." || line == ".." {
			return nil, &EnvConfigError{fmt.Sprintf("malformed env/index entry: %q", line)}
		}
		names = append(names, line)
	}
	return names, nil
}

// ListingEnabled parses root/env/listing per runtime.md §7.6; absent -> enabled.
func (fs *FS) ListingEnabled() (bool, error) {
	listingFile := filepath.Join(fs.root, "env", "listing")
	if _, err := os.Stat(listingFile); err != nil {
		return true, nil
	}
	lines, err := envConfigLines(listingFile)
	if err != nil {
		return false, err
	}
	if len(lines) != 1 || (lines[0] != "on" && lines[0] != "off") {
		return false, &EnvConfigError{"malformed env/listing: expected single on/off token"}
	}
	return lines[0] == "on", nil
}

// NotFoundError is returned when a path does not exist.
type NotFoundError struct{ msg string }

func (e *NotFoundError) Error() string { return e.msg }

// IsDirError is returned when a path is a directory but a file was expected.
type IsDirError struct{ msg string }

func (e *IsDirError) Error() string { return e.msg }

// EscapeError is returned when a path escapes the root.
type EscapeError struct{ msg string }

func (e *EscapeError) Error() string { return e.msg }

// SymlinkEscapeError is returned when a symlink escapes the root.
type SymlinkEscapeError struct{ msg string }

func (e *SymlinkEscapeError) Error() string { return e.msg }

// PathSegmentError is returned for invalid path segments.
type PathSegmentError struct{ msg string }

func (e *PathSegmentError) Error() string { return e.msg }

// ResourceKind indicates file or directory.
type ResourceKind string

const (
	KindFile      ResourceKind = "file"
	KindDirectory ResourceKind = "directory"
)

// Resource represents a resolved filesystem resource.
type Resource struct {
	Kind    ResourceKind
	Path    string // Absolute filesystem path
	RelPath string // Relative to root (as posix)
}

// ResourceType is kept for backward compat with server.go.
type ResourceType int

const (
	TypeNotFound ResourceType = iota
	TypeFile
	TypeDir
)

// FS provides filesystem operations within a root directory.
type FS struct {
	root string
}

// New creates a new filesystem handler for the given root.
func New(root string) *FS {
	absRoot, err := filepath.Abs(root)
	if err != nil {
		absRoot = root
	}
	return &FS{root: absRoot}
}

// Root returns the absolute root directory.
func (fs *FS) Root() string { return fs.root }

// PercentDecodeSegment decodes one raw URL path segment.
// If forFilesystem is true, decoded '/' or NUL are rejected.
func PercentDecodeSegment(raw string, forFilesystem bool) (string, error) {
	decoded, err := url.PathUnescape(raw)
	if err != nil {
		return "", &PathSegmentError{fmt.Sprintf("invalid percent-encoding in %q: %v", raw, err)}
	}
	if forFilesystem && (strings.Contains(decoded, "/") || strings.Contains(decoded, "\x00")) {
		return "", &PathSegmentError{fmt.Sprintf("decoded / or NUL in filesystem path segment: %q", raw)}
	}
	return decoded, nil
}

// isUnderRoot returns true if path is under root (after resolving).
func isUnderRoot(root, p string) bool {
	rootNorm := filepath.Clean(root)
	pNorm := filepath.Clean(p)
	return pNorm == rootNorm || strings.HasPrefix(pNorm, rootNorm+string(filepath.Separator))
}

// lookupChild finds a directory entry, with optional case-insensitive fallback.
func lookupChild(dir, name string, caseSensitive bool) (string, error) {
	direct := filepath.Join(dir, name)
	if _, err := os.Lstat(direct); err == nil {
		return direct, nil
	}
	if caseSensitive {
		return "", os.ErrNotExist
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}
	nameLower := strings.ToLower(name)
	for _, e := range entries {
		if strings.ToLower(e.Name()) == nameLower {
			return filepath.Join(dir, e.Name()), nil
		}
	}
	return "", os.ErrNotExist
}

// walkUnderRoot traverses rel_parts from root, respecting symlink policy.
// Returns the resolved absolute path, or nil if not found.
func walkUnderRoot(root string, relParts []string, symlinkPolicy string, caseSensitive bool) (string, error) {
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", fmt.Errorf("cannot resolve root: %w", err)
	}
	current := realRoot
	for _, part := range normalizeParts(relParts) {
		info, err := os.Lstat(current)
		if err != nil || !info.IsDir() {
			return "", nil
		}
		next, err := lookupChild(current, part, caseSensitive)
		if err != nil {
			return "", nil
		}
		linfo, err := os.Lstat(next)
		if err != nil {
			return "", nil
		}
		if linfo.Mode()&os.ModeSymlink != 0 {
			target, err := filepath.EvalSymlinks(next)
			if err != nil {
				return "", nil
			}
			switch symlinkPolicy {
			case "reject-escaping":
				if !isUnderRoot(realRoot, target) {
					return "", &SymlinkEscapeError{"symlink escapes root"}
				}
			case "unsupported":
				return "", &SymlinkEscapeError{"symlinks unsupported"}
			}
			current = target
		} else {
			current = next
		}
	}
	if !isUnderRoot(realRoot, current) {
		return "", &EscapeError{"path escapes root"}
	}
	return current, nil
}

func normalizeParts(parts []string) []string {
	var stack []string
	for _, p := range parts {
		if p == "" || p == "." {
			continue
		}
		if p == ".." {
			if len(stack) > 0 {
				stack = stack[:len(stack)-1]
			}
			continue
		}
		stack = append(stack, p)
	}
	return stack
}

// TryExactFilesystem checks if raw URL segments resolve to an exact filesystem resource.
// Returns nil (no error) if not found, error on escape/invalid, non-nil Resource if found.
func (fs *FS) TryExactFilesystem(rawSegments []string, caseSensitive bool, symlinkPolicy string) (*Resource, error) {
	if len(rawSegments) == 0 {
		info, err := os.Stat(fs.root)
		if err == nil && info.IsDir() {
			realRoot, _ := filepath.EvalSymlinks(fs.root)
			return &Resource{Kind: KindDirectory, Path: realRoot, RelPath: ""}, nil
		}
		return nil, nil
	}

	// Handle trailing query on last segment for exact filesystem check
	fsSegments := make([]string, len(rawSegments))
	copy(fsSegments, rawSegments)
	last := fsSegments[len(fsSegments)-1]
	if qIdx := strings.IndexByte(last, '?'); qIdx != -1 {
		nameOnly := last[:qIdx]
		queryRest := last[qIdx+1:]
		if !strings.Contains(queryRest, "/") {
			fsSegments[len(fsSegments)-1] = nameOnly
			if fsSegments[len(fsSegments)-1] == "" {
				return nil, nil
			}
		}
	}

	// Decode segments for filesystem lookup
	decoded := make([]string, 0, len(fsSegments))
	for _, raw := range fsSegments {
		d, err := PercentDecodeSegment(raw, true)
		if err != nil {
			return nil, nil // invalid encoding = no match
		}
		decoded = append(decoded, d)
	}

	resolved, err := walkUnderRoot(fs.root, decoded, symlinkPolicy, caseSensitive)
	if err != nil {
		switch err.(type) {
		case *SymlinkEscapeError, *EscapeError:
			return nil, nil // treat escape as not-found for exact check
		}
		return nil, err
	}
	if resolved == "" {
		return nil, nil
	}

	info, err := os.Stat(resolved)
	if err != nil {
		return nil, nil
	}

	realRoot, _ := filepath.EvalSymlinks(fs.root)
	relPath, _ := filepath.Rel(realRoot, resolved)
	if relPath == "." {
		relPath = ""
	}

	if info.IsDir() {
		return &Resource{Kind: KindDirectory, Path: resolved, RelPath: relPath}, nil
	}
	return &Resource{Kind: KindFile, Path: resolved, RelPath: relPath}, nil
}

// ReadFile reads the contents of a file.
func (fs *FS) ReadFile(absPath string) ([]byte, error) {
	return os.ReadFile(absPath)
}

// ImpliedCatBytes reads the bytes of the input suffix (the rightmost file resource).
func (fs *FS) ImpliedCatBytes(rawSegments []string, caseSensitive bool, symlinkPolicy string) ([]byte, error) {
	if len(rawSegments) == 0 {
		return []byte{}, nil
	}
	decoded := make([]string, 0, len(rawSegments))
	for _, raw := range rawSegments {
		d, err := PercentDecodeSegment(raw, true)
		if err != nil {
			return nil, fmt.Errorf("invalid path segment: %w", err)
		}
		decoded = append(decoded, d)
	}
	resolved, err := walkUnderRoot(fs.root, decoded, symlinkPolicy, caseSensitive)
	if err != nil {
		return nil, fmt.Errorf("input suffix error: %w", err)
	}
	if resolved == "" {
		return nil, &NotFoundError{fmt.Sprintf("input suffix not found: %s", strings.Join(decoded, "/"))}
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return nil, &NotFoundError{fmt.Sprintf("input suffix not found: %v", err)}
	}
	if info.IsDir() {
		return nil, &IsDirError{fmt.Sprintf("input suffix is a directory: %s", resolved)}
	}
	return os.ReadFile(resolved)
}

// DirectoryListing returns a text/plain listing of a directory (sorted).
func (fs *FS) DirectoryListing(absPath string) ([]byte, error) {
	entries, err := os.ReadDir(absPath)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() {
			name += "/"
		}
		names = append(names, name)
	}
	sort.Strings(names)
	body := strings.Join(names, "\n")
	if len(names) > 0 {
		body += "\n"
	}
	return []byte(body), nil
}

// FindIndexFile finds an index file in a directory.
func (fs *FS) FindIndexFile(absPath string, indexNames []string) string {
	for _, name := range indexNames {
		candidate := filepath.Join(absPath, name)
		info, err := os.Stat(candidate)
		if err == nil && info.Mode().IsRegular() {
			return candidate
		}
	}
	return ""
}

// PutFile writes data to a root-relative path (creating parents if needed).
func (fs *FS) PutFile(relParts []string, data []byte, createParents bool, symlinkPolicy string) error {
	realRoot, err := filepath.EvalSymlinks(fs.root)
	if err != nil {
		return fmt.Errorf("cannot resolve root: %w", err)
	}
	normalized := normalizeParts(relParts)
	if len(normalized) == 0 {
		return &EscapeError{"cannot PUT root directory"}
	}

	current := realRoot
	for _, part := range normalized[:len(normalized)-1] {
		current = filepath.Join(current, part)
		// Check symlink escape at each step
		linfo, lerr := os.Lstat(current)
		if lerr == nil && linfo.Mode()&os.ModeSymlink != 0 {
			resolved, rerr := filepath.EvalSymlinks(current)
			if rerr != nil {
				return fmt.Errorf("symlink resolution error: %w", rerr)
			}
			if symlinkPolicy == "reject-escaping" && !isUnderRoot(realRoot, resolved) {
				return &SymlinkEscapeError{"symlink escapes root"}
			}
		}
		if !isUnderRoot(realRoot, current) {
			return &EscapeError{"path escapes root"}
		}
	}
	target := filepath.Join(current, normalized[len(normalized)-1])
	if !isUnderRoot(realRoot, target) {
		return &EscapeError{"path escapes root"}
	}

	// Check target symlink escape
	if linfo, lerr := os.Lstat(target); lerr == nil && linfo.Mode()&os.ModeSymlink != 0 {
		resolved, rerr := filepath.EvalSymlinks(target)
		if rerr == nil && symlinkPolicy == "reject-escaping" && !isUnderRoot(realRoot, resolved) {
			return &SymlinkEscapeError{"symlink escapes root"}
		}
	}

	if createParents {
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return fmt.Errorf("mkdir failed: %w", err)
		}
	} else if _, err := os.Stat(filepath.Dir(target)); os.IsNotExist(err) {
		return &os.PathError{Op: "mkdir", Path: filepath.Dir(target), Err: os.ErrNotExist}
	}

	return os.WriteFile(target, data, 0o644)
}

// DeleteFile deletes a root-relative file.
func (fs *FS) DeleteFile(relParts []string, symlinkPolicy string) error {
	resolved, err := walkUnderRoot(fs.root, relParts, symlinkPolicy, true)
	if err != nil {
		switch err.(type) {
		case *SymlinkEscapeError:
			return err
		case *EscapeError:
			return err
		}
		return err
	}
	if resolved == "" {
		return &os.PathError{Op: "remove", Path: strings.Join(relParts, "/"), Err: os.ErrNotExist}
	}
	info, err := os.Stat(resolved)
	if err != nil || info.IsDir() {
		return &os.PathError{Op: "remove", Path: resolved, Err: os.ErrNotExist}
	}
	return os.Remove(resolved)
}

// InferMIMEType resolves Content-Type per runtime.md §6.1 resolution order.
func (fs *FS) InferMIMEType(absPath string) (string, error) {
	ext := strings.ToLower(filepath.Ext(absPath))
	mapping, declaredDefault, err := fs.LoadMIMEConfig()
	if err != nil {
		return "", err
	}
	if m, ok := mapping[ext]; ok {
		return m, nil
	}
	if declaredDefault != "" {
		return declaredDefault, nil
	}
	if m, ok := fallbackMIMETable[ext]; ok {
		return m, nil
	}
	return mimeDefault, nil
}

// InferMIMEFromBytes returns a MIME type from declared type or content sniff.
func InferMIMEFromBytes(data []byte, declared string) string {
	if declared != "" {
		return declared
	}
	if len(data) == 0 {
		return "text/plain"
	}
	// Try to interpret as UTF-8 text
	for _, b := range data {
		if b > 127 || (b < 32 && b != '\t' && b != '\n' && b != '\r') {
			return mimeDefault
		}
	}
	return "text/plain"
}

// SplitRawTargetForMutation strips query from raw target and splits for PUT/DELETE.
func SplitRawTargetForMutation(rawTarget string) []string {
	// Strip query (everything after first ?)
	if qIdx := strings.IndexByte(rawTarget, '?'); qIdx != -1 {
		rawTarget = rawTarget[:qIdx]
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

// decodePath percent-decodes a full URL path (kept for legacy use).
func decodePath(p string) (string, error) {
	return url.PathUnescape(p)
}

// splitPath splits on /, collapsing empty segments.
func splitPath(p string) []string {
	var result []string
	for _, seg := range strings.Split(p, "/") {
		if seg != "" {
			result = append(result, seg)
		}
	}
	return result
}

// containsDotDot returns true if any segment is "..".
func containsDotDot(segments []string) bool {
	for _, s := range segments {
		if s == ".." {
			return true
		}
	}
	return false
}

// checkEscape verifies a full path does not escape root (for legacy callers).
func (fs *FS) checkEscape(fullPath string) error {
	realPath, err := filepath.EvalSymlinks(fullPath)
	if err != nil {
		if os.IsNotExist(err) {
			return fs.checkParentEscape(fullPath)
		}
		return err
	}
	realRoot, err := filepath.EvalSymlinks(fs.root)
	if err != nil {
		return err
	}
	if !isUnderRoot(realRoot, realPath) {
		return &EscapeError{"path escapes root directory"}
	}
	return nil
}

func (fs *FS) checkParentEscape(fullPath string) error {
	dir := filepath.Dir(fullPath)
	realDir, err := filepath.EvalSymlinks(dir)
	if err != nil {
		return err
	}
	realRoot, err := filepath.EvalSymlinks(fs.root)
	if err != nil {
		return err
	}
	if !isUnderRoot(realRoot, realDir) {
		return &EscapeError{"path escapes root directory"}
	}
	return nil
}

// ResolveExact is the legacy method used by server.go GET handler.
// It resolves a URL path (with query stripped) to a Resource for file serving.
func (fs *FS) ResolveExact(rawPath string) (*Resource, error) {
	// Strip query/fragment
	if idx := strings.IndexAny(rawPath, "?#"); idx != -1 {
		rawPath = rawPath[:idx]
	}
	decoded, err := decodePath(rawPath)
	if err != nil {
		return nil, fmt.Errorf("invalid encoding: %w", err)
	}
	if strings.Contains(decoded, "\x00") {
		return nil, fmt.Errorf("invalid path characters: NUL")
	}
	segments := splitPath(decoded)
	for _, seg := range segments {
		if strings.Contains(seg, "/") {
			return nil, fmt.Errorf("invalid segment: contains decoded slash")
		}
	}
	if containsDotDot(segments) {
		return nil, fmt.Errorf("path escapes root directory")
	}
	cleanPath := strings.Join(segments, "/")
	fullPath := filepath.Join(fs.root, filepath.Clean("/"+cleanPath))
	if err := fs.checkEscape(fullPath); err != nil {
		return nil, err
	}
	info, err := os.Stat(fullPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	if info.IsDir() {
		return &Resource{Kind: KindDirectory, Path: fullPath, RelPath: cleanPath}, nil
	}
	return &Resource{Kind: KindFile, Path: fullPath, RelPath: cleanPath}, nil
}

// ReadFileAt reads a file at an absolute path (kept for server.go use).
func (fs *FS) ReadFileAt(absPath string) ([]byte, error) {
	return os.ReadFile(absPath)
}

// ListDir returns sorted directory entries (kept for legacy server.go use).
func (fs *FS) ListDir(absPath string) ([]string, error) {
	entries, err := os.ReadDir(absPath)
	if err != nil {
		return nil, err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() {
			name += "/"
		}
		names = append(names, name)
	}
	sort.Strings(names)
	return names, nil
}
