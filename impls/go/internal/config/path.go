package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

// LoadCommandPath loads the command search path from env/path
// Returns a list of directory paths relative to root
func LoadCommandPath(root string) ([]string, error) {
	pathFile := filepath.Join(root, "env", "path")
	
	data, err := os.ReadFile(pathFile)
	if err != nil {
		if os.IsNotExist(err) {
			// No env/path file - return empty path
			return []string{}, nil
		}
		return nil, err
	}

	var paths []string
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// Each line is a directory relative to root
		paths = append(paths, line)
	}

	return paths, nil
}

// FindCommand searches for a command in the command path
// Returns the full path to the command executable if found
func FindCommand(root string, commandName string, pathDirs []string) (string, error) {
	// Search each directory in path
	for _, dir := range pathDirs {
		fullDir := filepath.Join(root, dir)
		cmdPath := filepath.Join(fullDir, commandName)
		
		info, err := os.Stat(cmdPath)
		if err != nil {
			continue // Not found or not accessible
		}
		
		// Must be a regular file (not directory) and executable
		if !info.IsDir() && (info.Mode()&0111 != 0 || isScript(cmdPath)) {
			return cmdPath, nil
		}
	}
	
	return "", os.ErrNotExist
}

// isScript checks if a file has a shebang (making it executable via interpreter)
func isScript(path string) bool {
	f, err := os.Open(path)
	if err != nil {
		return false
	}
	defer f.Close()
	
	buf := make([]byte, 2)
	_, err = f.Read(buf)
	if err != nil {
		return false
	}
	
	return string(buf) == "#!"
}
