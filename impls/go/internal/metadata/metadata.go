package metadata

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// CommandMetadata holds parsed metadata for a command
type CommandMetadata struct {
	Arity           interface{} // int or "*"
	InputMode       string
	OutputMode      string
	Methods         []string
	MIMEType        string
	Mutates         bool
	ParseMode       string
	StderrMode      string
	ExitMapping     ExitMapping
	Malformed       bool
	MalformedReason string
}

// ExitMapping holds exit code to HTTP status mappings
type ExitMapping struct {
	Explicit map[int]int
	Wildcard *int
}

// DefaultMetadata returns metadata with default values per PP-4-arity0-default
func DefaultMetadata() *CommandMetadata {
	return &CommandMetadata{
		Arity:      0,
		InputMode:  "stdin",
		OutputMode: "stdout",
		Methods:    []string{"GET"},
		ParseMode:  "normal",
		StderrMode: "discard",
		ExitMapping: ExitMapping{
			Explicit: make(map[int]int),
		},
	}
}

// recognizedFields are the valid metadata field names
var recognizedFields = map[string]bool{
	"arity":      true,
	"input":      true,
	"output":     true,
	"methods":    true,
	"mime":       true,
	"mutates":    true,
	"parse-mode": true,
	"stderr":     true,
	"exit":       true,
}

// LoadMetadata loads metadata for a command from the root's env/meta directory
func LoadMetadata(root, commandName string) *CommandMetadata {
	meta := DefaultMetadata()
	metaPath := filepath.Join(root, "env", "meta", commandName)

	data, err := os.ReadFile(metaPath)
	if err != nil {
		// No metadata file - return defaults
		return meta
	}

	fields := make(map[string][]string)
	scanner := bufio.NewScanner(strings.NewReader(string(data)))

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.Fields(line)
		if len(parts) == 0 {
			continue
		}

		fieldName := parts[0]
		if !recognizedFields[fieldName] {
			continue // Skip unrecognized fields
		}

		fields[fieldName] = parts[1:]
	}

	// Apply fields
	for fieldName, values := range fields {
		if err := applyField(meta, fieldName, values); err != nil {
			meta.Malformed = true
			meta.MalformedReason = err.Error()
			return meta
		}
	}

	// Validate: GET permitted with mutates=true is invalid (PP-5.7-mutates-get-invalid)
	if contains(meta.Methods, "GET") && meta.Mutates {
		meta.Malformed = true
		meta.MalformedReason = "GET permitted with mutates true"
		return meta
	}

	return meta
}

func applyField(meta *CommandMetadata, name string, values []string) error {
	switch name {
	case "arity":
		if len(values) != 1 {
			return fmt.Errorf("arity requires exactly one value")
		}
		val := values[0]
		if val == "*" {
			meta.Arity = "*"
			return nil
		}
		n, err := strconv.Atoi(val)
		if err != nil {
			return fmt.Errorf("malformed arity: %s", val)
		}
		if n < 0 {
			return fmt.Errorf("negative arity: %d", n)
		}
		meta.Arity = n

	case "input":
		if len(values) != 1 {
			return fmt.Errorf("input requires exactly one value")
		}
		val := values[0]
		if val != "stdin" {
			return fmt.Errorf("malformed input: %s", val)
		}
		meta.InputMode = val

	case "output":
		if len(values) != 1 {
			return fmt.Errorf("output requires exactly one value")
		}
		val := values[0]
		if val != "stdout" {
			return fmt.Errorf("malformed output: %s", val)
		}
		meta.OutputMode = val

	case "methods":
		if len(values) == 0 {
			return fmt.Errorf("methods requires at least one value")
		}
		meta.Methods = values

	case "mime":
		if len(values) != 1 {
			return fmt.Errorf("mime requires exactly one value")
		}
		val := values[0]
		if !strings.Contains(val, "/") || strings.TrimSpace(val) != val || val == "" {
			return fmt.Errorf("malformed mime: %s", val)
		}
		meta.MIMEType = val

	case "mutates":
		if len(values) != 1 {
			return fmt.Errorf("mutates requires exactly one value")
		}
		switch values[0] {
		case "true":
			meta.Mutates = true
		case "false":
			meta.Mutates = false
		default:
			return fmt.Errorf("malformed mutates: %s", values[0])
		}

	case "parse-mode":
		if len(values) != 1 {
			return fmt.Errorf("parse-mode requires exactly one value")
		}
		val := values[0]
		if val != "normal" && val != "raw" {
			return fmt.Errorf("malformed parse-mode: %s", val)
		}
		meta.ParseMode = val

	case "stderr":
		if len(values) != 1 {
			return fmt.Errorf("stderr requires exactly one value")
		}
		val := values[0]
		if val != "discard" && val != "merge" {
			return fmt.Errorf("malformed stderr: %s", val)
		}
		meta.StderrMode = val

	case "exit":
		mapping := ExitMapping{Explicit: make(map[int]int)}
		for _, token := range values {
			if !strings.Contains(token, "=") {
				return fmt.Errorf("malformed exit pair: %s", token)
			}
			parts := strings.SplitN(token, "=", 2)
			codeStr, statusStr := parts[0], parts[1]

			status, err := strconv.Atoi(statusStr)
			if err != nil {
				return fmt.Errorf("malformed exit status: %s", statusStr)
			}

			if codeStr == "*" {
				mapping.Wildcard = &status
			} else {
				code, err := strconv.Atoi(codeStr)
				if err != nil {
					return fmt.Errorf("malformed exit code: %s", codeStr)
				}
				if code < 0 {
					return fmt.Errorf("negative exit code: %d", code)
				}
				mapping.Explicit[code] = status
			}
		}
		meta.ExitMapping = mapping
	}

	return nil
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

// MethodPermitted checks if a method is allowed by the metadata
func MethodPermitted(meta *CommandMetadata, method string) bool {
	return contains(meta.Methods, method)
}

// MapExitStatus maps an exit code to HTTP status per PP-5.4-exit-map
func MapExitStatus(meta *CommandMetadata, exitCode int) int {
	if exitCode == 0 {
		if status, ok := meta.ExitMapping.Explicit[0]; ok {
			return status
		}
		return 200
	}

	if status, ok := meta.ExitMapping.Explicit[exitCode]; ok {
		return status
	}

	if meta.ExitMapping.Wildcard != nil {
		return *meta.ExitMapping.Wildcard
	}

	return 400
}
