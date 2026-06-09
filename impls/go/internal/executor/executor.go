package executor

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/curtcox/wash/impls/go/internal/metadata"
)

// Stage represents a single command stage in a pipeline
type Stage struct {
	CommandPath string
	Argv        []string
	Meta        *metadata.CommandMetadata
}

// Pipeline represents a command pipeline
type Pipeline struct {
	Stages      []Stage
	InputSuffix string // May be empty
	RequestBody io.Reader // May be nil
}

// Result holds the execution result
type Result struct {
	ExitCode   int
	Output     []byte
	MIMEType   string
	HTTPStatus int
}

// Execute runs a pipeline and returns the result
func Execute(ctx context.Context, pipeline Pipeline) (*Result, error) {
	if len(pipeline.Stages) == 0 {
		return nil, fmt.Errorf("empty pipeline")
	}

	// For Phase 2: single stage execution only
	if len(pipeline.Stages) == 1 {
		return executeSingleStage(ctx, pipeline.Stages[0], pipeline.InputSuffix, pipeline.RequestBody)
	}

	// Multi-stage pipeline (Phase 3)
	return executeMultiStage(ctx, pipeline)
}

func executeSingleStage(ctx context.Context, stage Stage, inputSuffix string, body io.Reader) (*Result, error) {
	cmd := exec.CommandContext(ctx, stage.CommandPath, stage.Argv...)

	// Set up stdin
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stdin pipe: %w", err)
	}

	// Set up stdout/stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stdout pipe: %w", err)
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to create stderr pipe: %w", err)
	}

	// Start the command
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start command: %w", err)
	}

	// Feed input (suffix wins over body per RT-10.6-request-body)
	go func() {
		defer stdin.Close()
		if inputSuffix != "" {
			stdin.Write([]byte(inputSuffix))
		} else if body != nil {
			io.Copy(stdin, body)
		}
	}()

	// Collect output
	output, err := io.ReadAll(stdout)
	if err != nil {
		return nil, fmt.Errorf("failed to read stdout: %w", err)
	}

	// Handle stderr based on metadata
	stderrData, _ := io.ReadAll(stderr)
	_ = stderrData // TODO: handle merge vs discard

	// Wait for command to complete
	if err := cmd.Wait(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode := exitErr.ExitCode()
			httpStatus := metadata.MapExitStatus(stage.Meta, exitCode)
			return &Result{
				ExitCode:   exitCode,
				Output:     output,
				MIMEType:   determineMIMEType(stage.Meta, output),
				HTTPStatus: httpStatus,
			}, nil
		}
		return nil, fmt.Errorf("command failed: %w", err)
	}

	// Success
	httpStatus := metadata.MapExitStatus(stage.Meta, 0)
	return &Result{
		ExitCode:   0,
		Output:     output,
		MIMEType:   determineMIMEType(stage.Meta, output),
		HTTPStatus: httpStatus,
	}, nil
}

func executeMultiStage(ctx context.Context, pipeline Pipeline) (*Result, error) {
	// TODO: Phase 3 - implement multi-stage pipeline with plumbing
	return nil, fmt.Errorf("multi-stage pipelines not yet implemented")
}

func determineMIMEType(meta *metadata.CommandMetadata, output []byte) string {
	if meta.MIMEType != "" {
		return meta.MIMEType
	}
	return "text/plain; charset=utf-8"
}

// ResolveInterpreter finds the interpreter for a command based on exec rules
func ResolveInterpreter(commandPath string, rules []ExecRule) string {
	commandName := filepath.Base(commandPath)
	
	for _, rule := range rules {
		if matchPattern(rule.Pattern, commandName) {
			return rule.Interpreter
		}
	}
	
	return ""
}

// ExecRule represents a single exec rule
type ExecRule struct {
	Pattern     string
	Interpreter string
}

func matchPattern(pattern, name string) bool {
	if pattern == "*" {
		return true
	}
	if pattern == name {
		return true
	}
	
	// Simple glob matching
	if len(pattern) > 0 && pattern[0] == '*' {
		suffix := pattern[1:]
		return len(suffix) > 0 && len(name) >= len(suffix) && 
			name[len(name)-len(suffix):] == suffix
	}
	
	return false
}

// RunWithInterpreter runs a command using an interpreter
func RunWithInterpreter(interpreter string, scriptPath string, argv []string, stdin io.Reader) ([]byte, int, error) {
	args := append([]string{scriptPath}, argv...)
	cmd := exec.Command(interpreter, args...)
	
	if stdin != nil {
		cmd.Stdin = stdin
	}
	
	output, err := cmd.Output()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			return output, exitErr.ExitCode(), nil
		}
		return nil, -1, err
	}
	
	return output, 0, nil
}

// IsDirectExecutable checks if a file is directly executable (not via interpreter)
func IsDirectExecutable(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	
	// Check if it's a regular file with execute permission
	if info.IsDir() {
		return false
	}
	
	mode := info.Mode()
	return mode&0111 != 0
}
