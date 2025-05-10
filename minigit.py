"""
miniwyag.py: Minimal Git-like tool

Commands: init, hash-object, cat-file, add, commit, status, log, ls-objects, rm

Data Structures:
- GitRepository: Holds paths to the worktree and .minigit directory.
- GitObject: Base class for Git objects (Blob, Commit, Tree).
- GitBlob: Represents file contents.
- GitCommit: Represents a commit (tree, parent, author, message).
- GitTree: Represents a directory tree (not fully implemented, but stubbed for completeness).
- Index: Simple dict mapping file paths to blob SHAs (in-memory, written to .minigit/index as a text file).

Concepts and Programming Techniques Used:
- Classes & Inheritance: Used for GitObject, GitBlob, GitCommit, GitTree to model Git objects.
- Serialization/Deserialization: Custom methods to convert objects to/from bytes for storage.
- Hashing: SHA-1 hashing (via hashlib) to uniquely identify objects (like Git).
- Compression: zlib used to compress/decompress object data.
- File I/O: Reading/writing files for objects, index, and refs.
- Recursion: Used in cmd_add to recursively add files in directories.
- Sets & Dicts: Used for tracking index, staged, and untracked files.
- Simple Graph Traversal: The commit history is a singly-linked list (parent pointer), traversed in cmd_log.
- Command-line Parsing: argparse for CLI interface.
- Minimal Tree Structure: GitTree class stubbed for completeness (not fully implemented).
"""

import os
import sys
import hashlib
import zlib
import argparse
from datetime import datetime

# ----------------------
# Data Structures
# ----------------------

class GitRepository:
    def __init__(self, path):
        self.worktree = os.path.abspath(path)
        self.gitdir = os.path.join(self.worktree, ".minigit")

class GitObject:
    def serialize(self):
        raise NotImplementedError
    @classmethod
    def deserialize(cls, data):
        raise NotImplementedError

class GitBlob(GitObject):
    def __init__(self, data):
        self.data = data
    def serialize(self):
        return self.data
    @classmethod
    def deserialize(cls, data):
        return cls(data)

class GitCommit(GitObject):
    def __init__(self, tree, parent, author, message):
        self.tree = tree
        self.parent = parent
        self.author = author
        self.message = message
    def serialize(self):
        lines = [f"tree {self.tree}"]
        if self.parent:
            lines.append(f"parent {self.parent}")
        lines.append(f"author {self.author}")
        lines.append(f"committer {self.author}")
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode()
    @classmethod
    def deserialize(cls, data):
        lines = data.decode().splitlines()
        tree = None
        parent = None
        author = None
        message = []
        i = 0
        while i < len(lines):
            if lines[i].startswith("tree "):
                tree = lines[i][5:]
            elif lines[i].startswith("parent "):
                parent = lines[i][7:]
            elif lines[i].startswith("author "):
                author = lines[i][7:]
            elif lines[i] == "":
                message = "\n".join(lines[i+1:])
                break
            i += 1
        return cls(tree, parent, author, message)

class GitTree(GitObject):
    # Merkle-tree: list of (mode, path, sha)
    def __init__(self, entries):
        self.entries = entries  # list of (mode, path, sha)
    def serialize(self):
        # Format: for each entry "<mode> <path>\0" + raw SHA bytes
        result = b''
        for mode, path, sha in self.entries:
            header = f"{mode} {path}".encode() + b'\x00'
            sha_bytes = bytes.fromhex(sha)
            result += header + sha_bytes
        return result
    @classmethod
    def deserialize(cls, data):
        entries = []
        i = 0
        # Each entry: "mode path\0" + 20-byte SHA1
        while i < len(data):
            j = data.find(b'\x00', i)
            mode_path = data[i:j].decode()
            mode, path = mode_path.split(' ', 1)
            sha_bytes = data[j+1:j+21]
            entries.append((mode, path, sha_bytes.hex()))
            i = j + 21
        return cls(entries)

# Index: simple text file mapping relpath to blob sha
# Example line: "second_file.txt 123abc..."
def read_index(repo):
    index_path = os.path.join(repo.gitdir, "index")
    index = {}
    if os.path.exists(index_path):
        with open(index_path) as f:
            for line in f:
                path, sha = line.strip().split()
                index[path] = sha
    return index

def write_index(repo, index):
    index_path = os.path.join(repo.gitdir, "index")
    with open(index_path, "w") as f:
        for path, sha in index.items():
            f.write(f"{path} {sha}\n")

# ----------------------
# Utility Functions
# ----------------------

def repo_create(path):
    os.makedirs(path, exist_ok=True)
    gitdir = os.path.join(path, ".minigit")
    os.makedirs(gitdir, exist_ok=True)
    os.makedirs(os.path.join(gitdir, "objects"), exist_ok=True)
    with open(os.path.join(gitdir, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")
    os.makedirs(os.path.join(gitdir, "refs", "heads"), exist_ok=True)
    print(f"[miniwyag] Initialized empty repository at {os.path.abspath(gitdir)}")

def object_write(obj, repo, fmt):
    data = obj.serialize()
    header = f"{fmt} {len(data)}".encode() + b'\x00'
    full = header + data
    sha = hashlib.sha1(full).hexdigest()
    obj_path = os.path.join(repo.gitdir, "objects", sha[:2], sha[2:])
    obj_dir = os.path.dirname(obj_path)
    os.makedirs(obj_dir, exist_ok=True)
    if not os.path.exists(obj_path):
        with open(obj_path, "wb") as f:
            f.write(zlib.compress(full))
    return sha

def object_read(repo, sha):
    obj_path = os.path.join(repo.gitdir, "objects", sha[:2], sha[2:])
    if not os.path.exists(obj_path):
        raise Exception(f"Object {sha} not found.")
    with open(obj_path, "rb") as f:
        full = zlib.decompress(f.read())
    x = full.find(b' ')
    y = full.find(b'\x00', x)
    fmt = full[:x]
    size = int(full[x+1:y])
    data = full[y+1:]
    if fmt == b'blob':
        return GitBlob.deserialize(data)
    elif fmt == b'commit':
        return GitCommit.deserialize(data)
    elif fmt == b'tree':
        return GitTree.deserialize(data)
    else:
        raise Exception(f"Unknown object type: {fmt}")

# ----------------------
# Commands
# ----------------------

def cmd_init(args):
    repo_create(args.path)

def cmd_hash_object(args):
    repo = GitRepository(os.getcwd())
    with open(args.file, "rb") as f:
        data = f.read()
    blob = GitBlob(data)
    sha = object_write(blob, repo, "blob")
    print(sha)

def cmd_cat_file(args):
    repo = GitRepository(os.getcwd())
    obj = object_read(repo, args.sha)
    if args.type == "blob":
        sys.stdout.buffer.write(obj.data)
    elif args.type == "commit":
        print(obj.serialize().decode())
    else:
        print("Unsupported type for cat-file.")

def cmd_add(args):
    repo = GitRepository(os.getcwd())
    index = read_index(repo)
    # Build set of tracked files (from index and last commit)
    head_ref = os.path.join(repo.gitdir, "refs", "heads", "master")
    tracked = set(index.keys())
    if os.path.exists(head_ref):
        with open(head_ref) as f:
            sha = f.read().strip()
        if sha:
            commit = object_read(repo, sha)
            msg = commit.message
            if "[files]" in msg:
                files_section = msg.split("[files]", 1)[1]
                tracked |= set(line.strip() for line in files_section.strip().splitlines() if line.strip())
    def add_path(path):
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                # Skip .minigit directory
                if '.minigit' in root:
                    continue
                for f in files:
                    add_path(os.path.join(root, f))
        elif os.path.isfile(path):
            relpath = os.path.relpath(path, repo.worktree)
            if relpath in tracked:
                return  # Skip already tracked files
            with open(path, "rb") as f:
                data = f.read()
            blob = GitBlob(data)
            sha = object_write(blob, repo, "blob")
            index[relpath] = sha
            print(f"Added {relpath} (blob SHA: {sha})")
    for path in args.files:
        add_path(path)
    write_index(repo, index)

def cmd_rm(args):
    """
    Remove specified files from the index (untrack them).
    """
    repo = GitRepository(os.getcwd())
    index = read_index(repo)
    removed = False
    for path in args.files:
        relpath = os.path.relpath(path, repo.worktree)
        if relpath in index:
            del index[relpath]
            print(f"Untracked {relpath}")
            removed = True
        else:
            print(f"{relpath} is not tracked.")
    if removed:
        write_index(repo, index)

def cmd_commit(args):
    repo = GitRepository(os.getcwd())
    index = read_index(repo)
    # Get tracked files from last commit
    head_ref = os.path.join(repo.gitdir, "refs", "heads", "master")
    os.makedirs(os.path.dirname(head_ref), exist_ok=True)  # Ensure directory exists
    parent = None
    prev_tracked = {}
    if os.path.exists(head_ref):
        with open(head_ref) as f:
            parent = f.read().strip() or None
        if parent:
            commit = object_read(repo, parent)
            msg = commit.message
            if "[files]" in msg:
                files_section = msg.split("[files]", 1)[1]
                for line in files_section.strip().splitlines():
                    if line.strip():
                        # Each line is a file path
                        path = line.strip()
                        # Try to get the blob sha from the previous commit's tree (not implemented, so fallback to index)
                        # In a real implementation, parse the tree object. Here, we just keep the path.
                        prev_tracked[path] = None  # Value not used, just track the path
    # Merge previous tracked files with current index
    # If a file is in index, use the new blob sha; if only in prev_tracked, keep it; if removed from index, drop it
    new_tracked = dict(prev_tracked)
    for k in index:
        new_tracked[k] = index[k]
    # Remove files that were removed from index (rm command)
    for k in list(new_tracked.keys()):
        if k not in index and k not in prev_tracked:
            del new_tracked[k]
    if not new_tracked:
        print("Nothing to commit.")
        return
    # Build real tree entries from tracked files
    entries = []
    for path, blob_sha in sorted(new_tracked.items()):
        if blob_sha is None:
            continue  # skip unstaged/unhashed files
        mode = "100644"
        entries.append((mode, path, blob_sha))
    tree = GitTree(entries)
    tree_sha = object_write(tree, repo, "tree")
    author = f"{os.getenv('USER', 'user')} <{os.getenv('USER', 'user')}@localhost>"
    message = args.message or f"Commit at {datetime.now()}"
    # Store file list in commit message for demo
    message += "\n\n[files]\n" + "\n".join(sorted(new_tracked.keys()))
    commit = GitCommit(tree_sha, parent, author, message)
    commit_sha = object_write(commit, repo, "commit")
    with open(head_ref, "w") as f:
        f.write(commit_sha + "\n")
    print(f"Committed as {commit_sha}")
    write_index(repo, {})  # Clear the index after commit

def cmd_status(args):
    repo = GitRepository(os.getcwd())
    index = read_index(repo)
    # Get tracked files from last commit
    head_ref = os.path.join(repo.gitdir, "refs", "heads", "master")
    tracked = set()
    if os.path.exists(head_ref):
        with open(head_ref) as f:
            sha = f.read().strip()
        if sha:
            commit = object_read(repo, sha)
            msg = commit.message
            if "[files]" in msg:
                files_section = msg.split("[files]", 1)[1]
                tracked = set(line.strip() for line in files_section.strip().splitlines() if line.strip())
    print("Staged files:")
    for path in sorted(index.keys()):
        print(f"  {path}")
    # Find untracked files
    all_files = set()
    for root, _, files in os.walk(repo.worktree):
        if root.startswith(repo.gitdir):
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), repo.worktree)
            all_files.add(rel)
    untracked = sorted(all_files - tracked - set(index.keys()))
    print("Untracked files:")
    for path in untracked:
        print(f"  {path}")

def cmd_log(args):
    """
    Simple graph traversal: Each commit points to its parent (linked list).
    Traverses history from HEAD back to root.
    """
    repo = GitRepository(os.getcwd())
    head_ref = os.path.join(repo.gitdir, "refs", "heads", "master")
    if args.sha:
        sha = args.sha
    elif os.path.exists(head_ref):
        with open(head_ref) as f:
            sha = f.read().strip()
    else:
        print("No commits found.")
        return
    seen = set()
    while sha and sha not in seen:
        seen.add(sha)
        try:
            commit = object_read(repo, sha)  # Uses GitCommit
        except Exception as e:
            print(f"Broken commit {sha}: {e}")
            break
        print(f"commit {sha}")
        print(f"Author: {commit.author}")
        print(f"Message: {commit.message}\n")
        sha = commit.parent

def cmd_ls_objects(args):
    """
    List all objects in the object database (blobs, commits, trees).
    Uses: GitRepository, object_read, GitBlob, GitCommit, GitTree
    """
    repo = GitRepository(os.getcwd())
    objects_dir = os.path.join(repo.gitdir, "objects")
    for d in sorted(os.listdir(objects_dir)):
        if len(d) != 2:
            continue
        subdir = os.path.join(objects_dir, d)
        for f in sorted(os.listdir(subdir)):
            sha = d + f
            try:
                obj = object_read(repo, sha)
                if isinstance(obj, GitCommit):
                    typ = "commit"
                elif isinstance(obj, GitBlob):
                    typ = "blob"
                elif isinstance(obj, GitTree):
                    typ = "tree"
                else:
                    typ = "unknown"
                print(f"{sha} {typ}")
            except Exception:
                print(f"{sha} (unreadable)")

# ----------------------
# Argument Parser
# ----------------------

def main():
    parser = argparse.ArgumentParser(description="miniwyag: minimal git-like tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize a new repository")
    p_init.add_argument("path", nargs="?", default=".", help="Directory to initialize")
    p_init.set_defaults(func=cmd_init)

    p_hash = subparsers.add_parser("hash-object", help="Hash a file as a blob")
    p_hash.add_argument("file", help="File to hash")
    p_hash.set_defaults(func=cmd_hash_object)

    p_cat = subparsers.add_parser("cat-file", help="Show object content")
    p_cat.add_argument("type", choices=["blob", "commit"], help="Type of object")
    p_cat.add_argument("sha", help="SHA of object")
    p_cat.set_defaults(func=cmd_cat_file)

    p_add = subparsers.add_parser("add", help="Add file(s) to index")
    p_add.add_argument("files", nargs="+", help="Files to add")
    p_add.set_defaults(func=cmd_add)

    p_rm = subparsers.add_parser("rm", help="Remove file(s) from index (untrack)")
    p_rm.add_argument("files", nargs="+", help="Files to untrack")
    p_rm.set_defaults(func=cmd_rm)

    p_commit = subparsers.add_parser("commit", help="Commit staged files")
    p_commit.add_argument("-m", "--message", help="Commit message")
    p_commit.set_defaults(func=cmd_commit)

    p_status = subparsers.add_parser("status", help="Show staged and untracked files")
    p_status.set_defaults(func=cmd_status)

    p_log = subparsers.add_parser("log", help="Show commit history")
    p_log.add_argument("sha", nargs="?", help="Start from this commit SHA (default: HEAD)")
    p_log.set_defaults(func=cmd_log)

    p_lsobj = subparsers.add_parser("ls-objects", help="List all objects in the database")
    p_lsobj.set_defaults(func=cmd_ls_objects)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
