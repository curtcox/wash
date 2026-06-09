package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/curtcox/wash/impls/go/internal/server"
)

func main() {
	var (
		root = flag.String("root", ".", "Root directory to serve")
		port = flag.Int("port", 8080, "Port to listen on")
		host = flag.String("host", "127.0.0.1", "Host to bind to")
	)
	flag.Parse()

	if err := validateRoot(*root); err != nil {
		log.Fatalf("Invalid root directory: %v", err)
	}

	addr := fmt.Sprintf("%s:%d", *host, *port)
	srv := server.New(*root, addr)

	log.Printf("wash server starting on http://%s (root: %s)", addr, *root)
	if err := srv.Start(); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}

func validateRoot(root string) error {
	info, err := os.Stat(root)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		return fmt.Errorf("%s is not a directory", root)
	}
	return nil
}
