// Package executor runs command pipelines per specs/runtime.md and pipeline_parsing.md.
package executor

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/curtcox/wash/impls/go/internal/metadata"
	"github.com/curtcox/wash/impls/go/internal/parser"
)

// ExecutionError is returned for server-side execution failures.
type ExecutionError struct {
	Message string
	Status  int
}

func (e *ExecutionError) Error() string { return e.Message }

// ExecRule represents a single interpreter rule.
type ExecRule struct {
	Pattern     string
	Interpreter string
	ExtraArgs   []string
}

// ExecConfig holds the parsed exec rules for a root.
type ExecConfig struct {
	Rules           []ExecRule
	Malformed       bool
	MalformedReason string
}

// StageResult holds the result of one command stage execution.
type StageResult struct {
	Name       string
	ExitCode   int
	Stdout     []byte
	Stderr     []byte
	HTTPStatus int
}

// PipelineResult holds the result of a full pipeline execution.
type PipelineResult struct {
	Stdout              []byte
	Stderr              []byte
	ContentType         string
	Stages              []*StageResult
	PipelineDescription string
	SourcePath          string
	FinalCommand        string
	FailingStage        *StageResult
	HTTPStatus          int
}

// hasGlob returns true if the pattern contains glob metacharacters.
func hasGlob(pattern string) bool {
	return strings.ContainsAny(pattern, "*?[")
}

// ruleMatches checks if an exec rule matches a command path.
func ruleMatches(rule ExecRule, cmdPath string, commandDirs []string) bool {
	basename := filepath.Base(cmdPath)
	if !hasGlob(rule.Pattern) {
		return basename == rule.Pattern
	}
	matched, _ := filepath.Match(rule.Pattern, basename)
	if matched {
		return true
	}
	// Also try matching against path relative to its command dir
	for _, dir := range commandDirs {
		rel, err := filepath.Rel(dir, cmdPath)
		if err == nil && !strings.HasPrefix(rel, "..") {
			relMatched, _ := filepath.Match(rule.Pattern, filepath.ToSlash(rel))
			if relMatched {
				return true
			}
		}
	}
	return false
}

// ResolveInvocation returns the argv prefix to run the given command.
// Implements RT-7.2-exec-rules and RT-15.5-interpreter-fail.
func ResolveInvocation(cmdPath string, commandDirs []string, cfg ExecConfig) ([]string, error) {
	if cfg.Malformed {
		return nil, &ExecutionError{
			Message: cfg.MalformedReason,
			Status:  500,
		}
	}

	// Directly executable?
	if info, err := os.Stat(cmdPath); err == nil && !info.IsDir() {
		if info.Mode()&0111 != 0 {
			return []string{cmdPath}, nil
		}
	}

	for _, rule := range cfg.Rules {
		if ruleMatches(rule, cmdPath, commandDirs) {
			args := make([]string, 0, 2+len(rule.ExtraArgs))
			args = append(args, rule.Interpreter)
			args = append(args, rule.ExtraArgs...)
			args = append(args, cmdPath)
			return args, nil
		}
	}

	// Last resort: try running directly anyway (e.g. executable without x-bit checked above)
	if _, err := os.Stat(cmdPath); err == nil {
		return []string{cmdPath}, nil
	}

	return nil, &ExecutionError{
		Message: fmt.Sprintf("could not resolve interpreter for command %s", filepath.Base(cmdPath)),
		Status:  500,
	}
}

// runProcess executes a command and returns (exitCode, stdout, stderr).
func runProcess(argv []string, cwd string, stdinData []byte) (int, []byte, []byte, error) {
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Dir = cwd
	cmd.Env = os.Environ()

	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		return -1, nil, nil, fmt.Errorf("stdin pipe: %w", err)
	}

	outPipe, err := cmd.StdoutPipe()
	if err != nil {
		return -1, nil, nil, fmt.Errorf("stdout pipe: %w", err)
	}

	errPipe, err := cmd.StderrPipe()
	if err != nil {
		return -1, nil, nil, fmt.Errorf("stderr pipe: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return -1, nil, nil, fmt.Errorf("start: %w", err)
	}

	go func() {
		defer stdinPipe.Close()
		if len(stdinData) > 0 {
			stdinPipe.Write(stdinData)
		}
	}()

	stdoutBytes := readAll(outPipe)
	stderrBytes := readAll(errPipe)

	waitErr := cmd.Wait()
	exitCode := 0
	if waitErr != nil {
		if exitErr, ok := waitErr.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return -1, stdoutBytes, stderrBytes, waitErr
		}
	}
	return exitCode, stdoutBytes, stderrBytes, nil
}

// runProcessMerged runs a process with stderr merged into stdout.
func runProcessMerged(argv []string, cwd string, stdinData []byte) (int, []byte, error) {
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Dir = cwd
	cmd.Env = os.Environ()

	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		return -1, nil, fmt.Errorf("stdin pipe: %w", err)
	}

	outPipe, err := cmd.StdoutPipe()
	if err != nil {
		return -1, nil, fmt.Errorf("stdout pipe: %w", err)
	}
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		return -1, nil, fmt.Errorf("start: %w", err)
	}

	go func() {
		defer stdinPipe.Close()
		if len(stdinData) > 0 {
			stdinPipe.Write(stdinData)
		}
	}()

	out := readAll(outPipe)
	waitErr := cmd.Wait()
	exitCode := 0
	if waitErr != nil {
		if exitErr, ok := waitErr.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return -1, out, waitErr
		}
	}
	return exitCode, out, nil
}

func readAll(r interface{ Read([]byte) (int, error) }) []byte {
	if r == nil {
		return nil
	}
	var buf []byte
	tmp := make([]byte, 32*1024)
	for {
		n, err := r.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	return buf
}

func stderrMergeEnabled(stage *parser.CommandStage) bool {
	return stage.StderrMergeBoundary || stage.Meta.StderrMode == "merge"
}

// ExecuteRawCommand runs a parse-mode raw command.
func ExecuteRawCommand(raw *parser.RawCommandParse, root string, commandDirs []string, cfg ExecConfig, body []byte) (*PipelineResult, error) {
	stage := raw.Stage
	invocation, err := ResolveInvocation(stage.CommandPath, commandDirs, cfg)
	if err != nil {
		return nil, err
	}
	invocation = append(invocation, raw.RawSuffix)

	var stdinData []byte
	if len(body) > 0 {
		stdinData = body
	}

	merge := stderrMergeEnabled(stage)
	var exitCode int
	var stdout, stderr []byte

	if merge {
		exitCode, stdout, err = runProcessMerged(invocation, root, stdinData)
		if err != nil {
			return nil, &ExecutionError{Message: fmt.Sprintf("command execution failed: %v", err), Status: 500}
		}
	} else {
		exitCode, stdout, stderr, err = runProcess(invocation, root, stdinData)
		if err != nil {
			return nil, &ExecutionError{Message: fmt.Sprintf("command execution failed: %v", err), Status: 500}
		}
	}

	httpStatus := metadata.MapExitStatus(stage.Meta, exitCode)
	sr := &StageResult{
		Name:       stage.Name,
		ExitCode:   exitCode,
		Stdout:     stdout,
		Stderr:     stderr,
		HTTPStatus: httpStatus,
	}
	ct := stage.Meta.MIMEType
	if ct == "" {
		ct = "text/plain"
	}
	var failStage *StageResult
	if httpStatus >= 400 {
		failStage = sr
	}
	return &PipelineResult{
		Stdout:              stdout,
		Stderr:              stderr,
		ContentType:         ct,
		Stages:              []*StageResult{sr},
		PipelineDescription: fmt.Sprintf("%s %s", stage.Name, raw.RawSuffix),
		FinalCommand:        stage.Name,
		FailingStage:        failStage,
		HTTPStatus:          httpStatus,
	}, nil
}

// ExecutePipeline executes a full pipeline (data flows right-to-left from input suffix).
func ExecutePipeline(pipeline *parser.PipelineParse, root string, commandDirs []string, cfg ExecConfig, body []byte, stdinData []byte) (*PipelineResult, error) {
	stages := pipeline.Stages
	if len(stages) == 0 {
		return nil, &ExecutionError{Message: "empty pipeline", Status: 500}
	}

	// Data flows right-to-left: reverse stages for execution order.
	dataFlowStages := make([]*parser.CommandStage, len(stages))
	for i, s := range stages {
		dataFlowStages[len(stages)-1-i] = s
	}

	currentInput := stdinData
	if currentInput == nil && len(body) > 0 {
		currentInput = body
	}

	var stageResults []*StageResult

	for _, stage := range dataFlowStages {
		invocation, err := ResolveInvocation(stage.CommandPath, commandDirs, cfg)
		if err != nil {
			return nil, err
		}
		invocation = append(invocation, stage.Argv...)

		merge := stderrMergeEnabled(stage)
		var exitCode int
		var stdout, stderr []byte

		if merge {
			exitCode, stdout, err = runProcessMerged(invocation, root, currentInput)
			if err != nil {
				return nil, &ExecutionError{Message: fmt.Sprintf("command execution failed: %v", err), Status: 500}
			}
		} else {
			exitCode, stdout, stderr, err = runProcess(invocation, root, currentInput)
			if err != nil {
				return nil, &ExecutionError{Message: fmt.Sprintf("command execution failed: %v", err), Status: 500}
			}
		}

		httpStatus := metadata.MapExitStatus(stage.Meta, exitCode)
		sr := &StageResult{
			Name:       stage.Name,
			ExitCode:   exitCode,
			Stdout:     stdout,
			Stderr:     stderr,
			HTTPStatus: httpStatus,
		}
		stageResults = append(stageResults, sr)
		currentInput = stdout
	}

	// Find first failing stage in URL order (RT-15.3-exit-status).
	resultByName := make(map[string]*StageResult, len(stageResults))
	for _, sr := range stageResults {
		resultByName[sr.Name] = sr
	}
	var firstFail *StageResult
	for _, stage := range stages {
		sr := resultByName[stage.Name]
		if sr != nil && sr.HTTPStatus >= 400 {
			firstFail = sr
			break
		}
	}

	finalStage := stages[0]
	ct := finalStage.Meta.MIMEType
	if ct == "" {
		ct = "text/plain"
	}

	if firstFail != nil {
		return &PipelineResult{
			Stdout:              firstFail.Stdout,
			Stderr:              firstFail.Stderr,
			ContentType:         ct,
			Stages:              stageResults,
			PipelineDescription: pipeline.PipelineDescription,
			SourcePath:          pipeline.SourcePath,
			FinalCommand:        finalStage.Name,
			FailingStage:        firstFail,
			HTTPStatus:          firstFail.HTTPStatus,
		}, nil
	}

	var finalOut []byte
	if currentInput != nil {
		finalOut = currentInput
	}
	return &PipelineResult{
		Stdout:              finalOut,
		Stderr:              nil,
		ContentType:         ct,
		Stages:              stageResults,
		PipelineDescription: pipeline.PipelineDescription,
		SourcePath:          pipeline.SourcePath,
		FinalCommand:        finalStage.Name,
		FailingStage:        nil,
		HTTPStatus:          200,
	}, nil
}
