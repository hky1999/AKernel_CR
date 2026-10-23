package firecracker

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestJuiceFSActualCloneHelper(t *testing.T) {
	root := os.Getenv("AKCR_CLONE_ROOT")
	nonce := os.Getenv("AKCR_CLONE_NONCE")
	if filepath.Dir(root) != "/mnt/akernel-shared" || filepath.Base(root) != "pr119-native-clone-"+nonce || nonce == "" {
		t.Fatal("wrong owned root")
	}
	info, err := os.Lstat(root)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		t.Fatal("root changed", err)
	}
	var owner struct {
		Nonce string
		Inode uint64
	}
	data, err := os.ReadFile(filepath.Join(root, "owner.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &owner); err != nil {
		t.Fatal(err)
	}
	st := info.Sys().(*syscall.Stat_t)
	var fs syscall.Statfs_t
	if err = syscall.Statfs(root, &fs); err != nil || fs.Type != 0x65735546 || owner.Nonce != nonce || owner.Inode != st.Ino {
		t.Fatal("ownership or FUSE mismatch", err)
	}
	src, dst := filepath.Join(root, "base"), filepath.Join(root, "go-actual-clone")
	role := os.Getenv("AKCR_CLONE_ROLE")
	switch role {
	case "copy":
		start := time.Now()
		reflinked, err := cloneFileNoSync(src, dst)
		if err != nil {
			t.Fatal(err)
		}
		copiedMS := float64(time.Since(start).Nanoseconds()) / 1e6
		f, err := os.OpenFile(dst, os.O_RDWR, 0)
		if err != nil {
			t.Fatal(err)
		}
		if err = f.Sync(); err != nil {
			f.Close()
			t.Fatal(err)
		}
		if err = f.Close(); err != nil {
			t.Fatal(err)
		}
		a, err := os.Stat(src)
		if err != nil {
			t.Fatal(err)
		}
		b, err := os.Stat(dst)
		if err != nil {
			t.Fatal(err)
		}
		if a.Size() != 67108864 || b.Size() != a.Size() || os.SameFile(a, b) || reflinked {
			t.Fatal("unexpected size, alias, or FICLONE success")
		}
		if _, err = cloneFileNoSync(src, dst); err == nil {
			t.Fatal("existing destination accepted")
		}
		msg, _ := json.Marshal(map[string]any{"role": role, "reflinked": reflinked, "logical_bytes": b.Size(), "helper_ms": copiedMS, "helper_plus_fsync_ms": float64(time.Since(start).Nanoseconds()) / 1e6, "exclusive_destination_rejected": true})
		fmt.Println("AKCR_GO_CLONE_RESULT " + string(msg))
	case "verify":
		for _, name := range []string{"base", "go-actual-clone"} {
			f, err := os.Open(filepath.Join(root, name))
			if err != nil {
				t.Fatal(err)
			}
			h := sha256.New()
			_, err = io.Copy(h, f)
			f.Close()
			if err != nil {
				t.Fatal(err)
			}
			if !strings.EqualFold(hex.EncodeToString(h.Sum(nil)), "6e0722a16ae40d8fe00a54d43f600ec337f45868d7a2c5277c65b9caaa06a2fb") {
				t.Fatal("full content differs", name)
			}
		}
		fmt.Println("AKCR_GO_CLONE_RESULT {\"role\":\"verify\",\"full_hashes_equal\":true}")
	default:
		t.Fatal("explicit role required")
	}
}
