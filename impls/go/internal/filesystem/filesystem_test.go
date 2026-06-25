package filesystem

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(wd, "go.mod")); err == nil && strings.HasSuffix(wd, filepath.Join("impls", "go")) {
			return filepath.Dir(filepath.Dir(wd))
		}
		next := filepath.Dir(wd)
		if next == wd {
			t.Fatal("repo root not found")
		}
		wd = next
	}
}

func TestResolveUnderRootNames(t *testing.T) {
	fs := New(filepath.Join(repoRoot(t), "harness", "roots", "names"))

	got, err := fs.ResolveUnderRoot([]string{"greeting"}, "reject-escaping", true)
	if err != nil {
		t.Fatalf("ResolveUnderRoot(greeting) error: %v", err)
	}
	want := filepath.Join(fs.Root(), "0", "a")
	if got != want {
		t.Fatalf("ResolveUnderRoot(greeting) = %q, want %q", got, want)
	}

	got, err = fs.ResolveUnderRoot([]string{"0", "greeting"}, "reject-escaping", true)
	if err != nil {
		t.Fatalf("ResolveUnderRoot(0/greeting) error: %v", err)
	}
	want = filepath.Join(fs.Root(), "0", "0", "a")
	if got != want {
		t.Fatalf("ResolveUnderRoot(0/greeting) = %q, want %q", got, want)
	}
}

func TestResolveUnderRootNameLoop(t *testing.T) {
	fs := New(filepath.Join(repoRoot(t), "harness", "roots", "names"))

	_, err := fs.ResolveUnderRoot([]string{"loopa"}, "reject-escaping", true)
	var loopErr *NameLoopError
	if err == nil || !strings.Contains(err.Error(), "depth") {
		t.Fatalf("ResolveUnderRoot(loopa) error = %v, want depth error", err)
	}
	if _, ok := err.(*NameLoopError); !ok {
		t.Fatalf("ResolveUnderRoot(loopa) error type = %T, want %T", err, loopErr)
	}
}
