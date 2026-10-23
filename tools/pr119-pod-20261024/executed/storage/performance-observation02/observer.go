// Diagnostic only. Build and execute on the remote isolated task.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"sync"
	"time"
)

const socket = "/tmp/pr119-observation.sock"

type stats struct {
	Samples       uint64 `json:"samples"`
	MaxMonoNS     int64  `json:"max_mono_gap_ns"`
	MaxWallNS     int64  `json:"max_wall_gap_ns"`
	BackwardsWall uint64 `json:"backwards_wall_samples"`
	IntervalNS    int64  `json:"interval_ns"`
}

func main() {
	if len(os.Args) != 2 {
		panic("serve, reset or stats required")
	}
	if os.Args[1] != "serve" {
		mode := os.Args[1]
		method := "GET"
		if mode == "reset" {
			method = "POST"
		} else if mode != "stats" {
			panic("unknown mode")
		}
		tr := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", socket)
		}}
		client := &http.Client{Transport: tr, Timeout: 10 * time.Second}
		req, err := http.NewRequest(method, "http://localhost/"+mode, nil)
		if err != nil {
			panic(err)
		}
		r, err := client.Do(req)
		if err != nil {
			panic(err)
		}
		defer r.Body.Close()
		if r.StatusCode != 200 {
			panic(fmt.Sprintf("observer HTTP %d", r.StatusCode))
		}
		if _, err = io.Copy(os.Stdout, r.Body); err != nil {
			panic(err)
		}
		return
	}
	var mu sync.Mutex
	value := stats{IntervalNS: 2000000}
	last := time.Now()
	listener, err := net.Listen("unix", socket)
	if err != nil {
		panic(err)
	}
	defer listener.Close()
	go func() {
		ticker := time.NewTicker(2 * time.Millisecond)
		defer ticker.Stop()
		for range ticker.C {
			mu.Lock()
			now := time.Now()
			mono := now.Sub(last).Nanoseconds()
			wall := now.UnixNano() - last.UnixNano()
			if mono > value.MaxMonoNS {
				value.MaxMonoNS = mono
			}
			if wall > value.MaxWallNS {
				value.MaxWallNS = wall
			}
			if wall < 0 {
				value.BackwardsWall++
			}
			value.Samples++
			last = now
			mu.Unlock()
		}
	}()
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.URL.Path == "/reset" && r.Method == "POST" {
			value = stats{IntervalNS: 2000000}
			last = time.Now()
		} else if r.URL.Path != "/stats" || r.Method != "GET" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(value)
	})
	server := http.Server{Handler: h, ReadHeaderTimeout: 5 * time.Second}
	if err = server.Serve(listener); err != nil {
		panic(err)
	}
}
