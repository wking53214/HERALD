"""Mutation harness. Runs ONLY against scratch copies; never touches the repo.
Usage: mutate.py <repo_root> <workdir_root> <out.json> [workers]
"""
import ast, copy, json, os, shutil, subprocess, sys, time, concurrent.futures as cf

REPO, WORK, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 4
PY = sys.executable
TARGETS = ["gate.py", "claim.py", "handoff.py", "boundary.py", "binding.py",
           "source.py", "lineage.py", "calibration.py", "extract.py", "ambiguity.py"]
CHECKISH = ("verify", "assert", "validate", "seal", "compare_digest")

SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
        ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
        ast.In: ast.NotIn, ast.NotIn: ast.In}

def sites(tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in SWAP: out.append(("cmp", node, i))
        elif isinstance(node, ast.BoolOp): out.append(("boolop", node, 0))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): out.append(("notdrop", node, 0))
        elif isinstance(node, ast.If): out.append(("ifneg", node, 0))
        elif isinstance(node, ast.Raise): out.append(("raise2pass", node, 0))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if any(k in name for k in CHECKISH): out.append(("calldrop", node, 0))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool): out.append(("boolconst", node, 0))
    return out

def apply(tree, idx):
    t = copy.deepcopy(tree)
    kind, target, sub = sites(t)[idx]
    desc = kind
    if kind == "cmp": target.ops[sub] = SWAP[type(target.ops[sub])]()
    elif kind == "boolop": target.op = ast.Or() if isinstance(target.op, ast.And) else ast.And()
    elif kind == "notdrop":
        for p in ast.walk(t):
            for f, v in ast.iter_fields(p):
                if v is target: setattr(p, f, target.operand)
                elif isinstance(v, list):
                    for j, x in enumerate(v):
                        if x is target: v[j] = target.operand
    elif kind == "ifneg": target.test = ast.UnaryOp(op=ast.Not(), operand=target.test)
    elif kind in ("raise2pass", "calldrop"):
        for p in ast.walk(t):
            for f, v in ast.iter_fields(p):
                if isinstance(v, list):
                    for j, x in enumerate(v):
                        if x is target: v[j] = ast.Pass()
    elif kind == "boolconst": target.value = not target.value
    ast.fix_missing_locations(t)
    return kind, getattr(target, "lineno", 0), ast.unparse(t)

def run(cwd, ignore_hulk=None, only_hulk=False):
    cmd = [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "--no-header", "-W", "ignore"]
    if only_hulk: cmd.append("Tests/test_hulk_100.py")
    elif ignore_hulk: cmd += ["Tests", "--ignore=Tests/test_hulk_100.py"]
    else: cmd.append("Tests")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90, env=env)
        return r.returncode          # 0 = survived, 1 = test failed, 2/3/4 = error
    except subprocess.TimeoutExpired:
        return "timeout"

def worker(wid, jobs):
    wd = os.path.join(WORK, f"w{wid}")
    shutil.rmtree(wd, ignore_errors=True)
    shutil.copytree(REPO, wd, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    res = []
    for fname, idx in jobs:
        path = os.path.join(wd, "herald", fname)
        orig = open(os.path.join(REPO, "herald", fname)).read()
        tree = ast.parse(orig)
        kind, line, mutated = apply(tree, idx)
        open(path, "w").write(mutated)
        try:
            rc_non = run(wd, ignore_hulk=True)
            if rc_non == 0:
                rc_hulk = run(wd, only_hulk=True)
                status = "survived" if rc_hulk == 0 else ("killed_only_by_hulk" if rc_hulk in (1, "timeout") else "error_hulk")
            elif rc_non in (1, "timeout"): status = "killed_by_other_tests"
            else: status = "error"
        finally:
            open(path, "w").write(orig)
        res.append({"file": fname, "site": idx, "op": kind, "line": line, "status": status})
    return res

if __name__ == "__main__":
    jobs = []
    for f in TARGETS:
        tree = ast.parse(open(os.path.join(REPO, "herald", f)).read())
        n = len(sites(tree))
        jobs += [(f, i) for i in range(n)]
    print("total mutants:", len(jobs), flush=True)
    chunks = [jobs[i::WORKERS] for i in range(WORKERS)]
    t0 = time.time(); allres = []
    with cf.ProcessPoolExecutor(WORKERS) as ex:
        for r in ex.map(worker, range(WORKERS), chunks): allres += r
    json.dump(allres, open(OUT, "w"), indent=1)
    from collections import Counter
    print(Counter(r["status"] for r in allres), f"{time.time()-t0:.0f}s")
