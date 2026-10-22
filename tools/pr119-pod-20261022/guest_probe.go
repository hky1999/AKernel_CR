// Independent acceptance helper. Build and execute on the remote test server only.
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"sync"
	"time"
)

type reply struct {
	HTTPStatus int    `json:"http_status"`
	Body       string `json:"body"`
	ElapsedMS  int64  `json:"elapsed_ms"`
}

func request(socket, path, method, body string, timeout time.Duration) (reply, error) {
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socket)
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: timeout}
	req, err := http.NewRequest(method, "http://localhost"+path, bytes.NewBufferString(body))
	if err != nil {
		return reply{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	start := time.Now()
	resp, err := client.Do(req)
	if err != nil {
		return reply{ElapsedMS: time.Since(start).Milliseconds()}, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	return reply{resp.StatusCode, string(data), time.Since(start).Milliseconds()}, err
}

func fillMemory(data []byte) {
	state := uint64(0x4a7c15bd29618e33)
	for i := range data {
		state ^= state << 13
		state ^= state >> 7
		state ^= state << 17
		data[i] = byte(state)
	}
}

type memoryState struct {
	mu    sync.Mutex
	data  []byte
	token string
	fd    *os.File
}

func (s *memoryState) snapshot() (map[string]any, error) {
	hash := sha256.Sum256(s.data)
	if _, err := s.fd.Seek(0, io.SeekStart); err != nil {
		return nil, err
	}
	content, err := io.ReadAll(s.fd)
	if err != nil {
		return nil, err
	}
	return map[string]any{"pid": os.Getpid(), "token": s.token, "memory_bytes": len(s.data),
		"sha256": hex.EncodeToString(hash[:]), "fd_content": string(content)}, nil
}

func (s *memoryState) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if r.URL.Path == "/mutate" && r.Method == http.MethodPost {
		for i := 0; i < len(s.data); i += 4096 {
			s.data[i] ^= 0xff
		}
		if err := s.fd.Truncate(0); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if _, err := s.fd.WriteAt([]byte("open-fd-after"), 0); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
	} else if r.URL.Path != "/state" || r.Method != http.MethodGet {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	state, err := s.snapshot()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(state); err != nil {
		fmt.Fprintln(os.Stderr, err)
	}
}

func run() error {
	if len(os.Args) < 2 {
		return fmt.Errorf("expected checkpoint, hold, state or mutate")
	}
	mode := os.Args[1]
	flags := flag.NewFlagSet(mode, flag.ContinueOnError)
	socket := flags.String("socket", "/tmp/internal-checkpoint-probe.sock", "Unix socket")
	body := flags.String("body", "{\"timeoutSeconds\":120}", "checkpoint JSON request")
	timeout := flags.Int("timeout", 150, "HTTP client timeout in seconds")
	size := flags.Int("bytes", 512<<20, "resident memory bytes")
	if err := flags.Parse(os.Args[2:]); err != nil {
		return err
	}
	if mode != "hold" {
		path, method := "/state", http.MethodGet
		if mode == "checkpoint" {
			path, method = "/checkpoint", http.MethodPost
		} else if mode == "mutate" {
			path, method = "/mutate", http.MethodPost
		} else if mode != "state" {
			return fmt.Errorf("unknown mode %q", mode)
		}
		result, err := request(*socket, path, method, *body, time.Duration(*timeout)*time.Second)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(result)
	}
	if *size < 1 || *size > 1<<30 {
		return fmt.Errorf("memory size outside 1..1GiB")
	}
	state := &memoryState{data: make([]byte, *size)}
	fillMemory(state.data)
	token := make([]byte, 16)
	if _, err := rand.Read(token); err != nil {
		return err
	}
	state.token = hex.EncodeToString(token)
	fd, err := os.OpenFile("/tmp/internal-checkpoint-held-fd", os.O_CREATE|os.O_EXCL|os.O_RDWR, 0o600)
	if err != nil {
		return err
	}
	defer fd.Close()
	state.fd = fd
	if _, err = fd.Write([]byte("open-fd-before")); err != nil {
		return err
	}
	listener, err := net.Listen("unix", *socket)
	if err != nil {
		return err
	}
	defer listener.Close()
	server := &http.Server{Handler: state, ReadHeaderTimeout: 5 * time.Second}
	return server.Serve(listener)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
