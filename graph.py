# plot_commit_graph.py

import sys
import os
from graphviz import Digraph

# adjust path so minigit.py is importable
sys.path.append(os.path.dirname(__file__))

from minigit import GitRepository, object_read, GitCommit

def plot_commit_graph(repo_path, output_path='commit_graph'):
    repo = GitRepository(repo_path)
    head_ref = os.path.join(repo.gitdir, 'refs', 'heads', 'master')
    with open(head_ref) as f:
        head_sha = f.read().strip()
    sha = head_sha
    dot = Digraph('miniwyag')
    seen = set()
    while sha and sha not in seen:
        seen.add(sha)
        commit = object_read(repo, sha)
        dot.node(sha, f"{sha[:7]}\n{commit.message.splitlines()[0]}", shape='box')
        # link commit → its tree
        dot.edge(sha, commit.tree, label="tree")        # Plot Merkle-tree for this commit
        plot_tree(repo, dot, commit.tree)
        if commit.parent:
            dot.edge(commit.parent, sha)
        sha = commit.parent
    dot.render(output_path, format='png', cleanup=True)

def plot_tree(repo, dot, tree_sha):
    tree = object_read(repo, tree_sha)  # GitTree
    dot.node(tree_sha, f"tree\n{tree_sha[:7]}", shape='oval')
    # Determine tree entries from GitTree
    if hasattr(tree, 'items'):
        entries = tree.items() if callable(tree.items) else tree.items
    elif hasattr(tree, 'entries'):
        entries = tree.entries
    else:
        entries = []
    for mode, path, sha in entries:
        label = f"{path}\n{sha[:7]}"
        shape = 'box' if mode.startswith('100') else 'oval'
        dot.node(sha, label, shape=shape)
        dot.edge(tree_sha, sha)
        if mode == '040000':
            plot_tree(repo, dot, sha)
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('repo', help='path to repo worktree')
    p.add_argument('--out', default='commit_graph', help='output name')
    args = p.parse_args()
    plot_commit_graph(args.repo, args.out)