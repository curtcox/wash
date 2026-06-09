package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

// ExecRule represents a single exec rule: pattern -> interpreter
type ExecRule struct {
	Pattern     string
	Interpreter string
}

// LoadExecRules loads interpreter rules from the exec file
// The exec file format is line-oriented: "pattern interpreter"
func LoadExecRules(root string) ([]ExecRule, error) {
	execFile := filepath.Join(root, "exec")
	
	data, err := os.ReadFile(execFile)
	if err != nil {
		if os.IsNotExist(err) {
			// No exec file - return empty rules
			return []ExecRule{}, nil
		}
		return nil, err
	}

	var rules []ExecRule
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		parts := strings.Fields(line)
		if len(parts) < 2 {
			continue // Malformed line - skip or could error
		}

		rules = append(rules, ExecRule{
			Pattern:     parts[0],
			Interpreter: parts[1],
		})
	}

	return rules, nil
}

// FindInterpreter finds the first matching interpreter for a command
// Returns empty string if no rule matches
func FindInterpreter(rules []ExecRule, commandName string) string {
	for _, rule := range rules {
		if matchPattern(rule.Pattern, commandName) {
			return rule.Interpreter
		}
	}
	return ""
}

// matchPattern checks if a command name matches a glob-like pattern
// Supports: * (any sequence), ? (single char)
func matchPattern(pattern, name string) bool {
	// Simple glob matching
	if pattern == "*" {
		return true
	}
	if pattern == name {
		return true
	}
	
	// Handle * wildcards
	if strings.Contains(pattern, "*") {
		parts := strings.Split(pattern, "*")
		if len(parts) == 2 {
			// pattern is "prefix*suffix"
			if strings.HasPrefix(name, parts[0]) && strings.HasSuffix(name, parts[1]) {
				return true
			}
		}
	}
	
	return false
}
