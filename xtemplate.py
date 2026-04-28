# xtemplate.py
# shae m puckett 2026
# MIT license

import sys, io

_nop5 = (False, False, None, None, None)
_nop4 = (False, False, None, None) 
_expected={2:'endif',4:'endwhile',5:'endfor'}
_safe_globals = {
    "__builtins__": {
        # type coercion
        "str": str, "int": int, "float": float, "bool": bool,
        "list": list, "dict": dict, "tuple": tuple, "set": set,
        # iteration
        "range": range, "enumerate": enumerate, "zip": zip,
        "len": len, "sorted": sorted, "reversed": reversed,
        "map": map, "filter": filter, "min": min, "max": max,
        "sum": sum, "any": any, "all": all,
        # strings
        "repr": repr, "chr": chr, "ord": ord,
        # misc safe
        "round": round, "abs": abs, "isinstance": isinstance,
        "print": print,  
    }
}
class XTemplateError(RuntimeError): pass
def _filesystem(path): return open(path,"r")
    
class XTemplate:
    def __init__(self, base_path = '/', chunk_size = 512, globals = _safe_globals, open_with = _filesystem, max_lines=10000, prefix = "#", throw = False):
        self.base_path = base_path
        self.chunk_size = chunk_size
        self.open_with = open_with
        self.globals = globals
        self.max_lines = max_lines
        self.prefix = prefix
        self.throw = throw

    def _render(self, path, lines_left, _locals):
        _globals = self.globals
        prefix = self.prefix
        comment = prefix + "#"
        fullpath = self.base_path + path
        stream = self.open_with(fullpath)
        try:
            def evaluate(expr): return eval(expr.strip(),_globals,_locals)
            
            stack = [(True, False)]     # stack structure [active, branch_taken, (loop data ...)]
            brkcnt = 0                  # n/a = 0, break = 1, continue = 2, >2 nested
            while True:
                lines_left -= 1         # generally counting statements only, not body text
                if lines_left <= 0: raise XTemplateError("runaway template expansion")
                stackend = stack[-1]
                loopactive = stackend[0]
                anyactive = loopactive and not brkcnt

                while True:                           # body text
                    line = stream.readline()
                    if not line: return               # eof
                    if hasattr(line,"decode"): line = line.decode()
                    if line.startswith(prefix): break # statement
                    if not anyactive: continue        # don't render 
                    c = 0
                    while True:
                      if 0 <= (s := line.find("{{",c)):
                        if 0 <= (e := line.find("}}",s+2)):
                          yield line[c:s] + str(evaluate(line[s+2:e]))
                          c = e + 2
                          continue
                      yield line[c:]
                      break
                
                if line.startswith(comment): continue # comment
                parts = line.split(None, 2)
                if len(parts) < 2: continue           # empty statement
                kw = parts[1]
                rest = parts[2] if len(parts) > 2 else ""

                if kw == "if":
                    cond = anyactive and bool(evaluate(rest))
                    stack.append([cond, cond]) # 2 elements

                elif kw == "elif":
                    if brkcnt: continue
                    if stack[-2][0] and not stackend[1]: # parent active but not taken
                        cond = bool(evaluate(rest))
                        stackend[0:2] = [cond, cond]
                    else:
                        stackend[0] = False

                elif kw == "else":
                    if brkcnt: continue
                    if len(stackend) != 2 and stackend[0]:
                        brkcnt = 2  # else for loops works
                    else:
                      stackend[0:2] = [stack[-2][0] and not stackend[1], True] # parent active, invert taken

                elif kw == "endif":
                    if len(stackend) != 2: raise XTemplateError(f"expected {_expected[len(stackend)]} not endif")
                    if len(stack) < 2: raise XTemplateError(f"unexpected endif")
                    stack.pop()

                elif kw == "for":
                    if not anyactive: 
                      stack.append(list(_nop5))
                      if brkcnt: brkcnt += 2  # pseudo stack effect
                    else:
                        v_in_e = rest.split(None, 2)
                        var, expr = v_in_e[0], v_in_e[2]
                        it = iter(evaluate(expr)) 
                        try: val = next(it)
                        except StopIteration: val = _nop4 # flag 
                        confirm = val is not _nop4
                        stack.append([confirm, confirm, var, it, stream.tell()]) # 5 elements
                        if confirm: _locals[var] = val

                elif kw == "endfor":
                    if len(stackend) != 5: raise XTemplateError(f"expected {_expected[len(stackend)]} not endfor")
                    if len(stack) < 2: raise XTemplateError(f"unexpected endfor")
                    term = not loopactive or brkcnt == 1
                    _, _, var, iterator, pos = stackend
                    if not term:
                        try:
                            _locals[var] = next(iterator)
                            stream.seek(pos)
                            stackend[0:2] = [True, True]
                        except StopIteration: term = True
                    if term: stack.pop()
                    brkcnt = 0 if brkcnt <= 2 else brkcnt - 2
            
                elif kw == "while":
                    if not anyactive: 
                        stack.append(list(_nop4))
                        if brkcnt: brkcnt += 2  # pseudo stack effect
                    else:
                        cond = bool(evaluate(rest))
                        stack.append([cond, cond, rest, stream.tell()]) # 4 elements

                elif kw == "endwhile":
                    if len(stackend) != 4: raise XTemplateError(f"expected {_expected[len(stackend)]} not endwhile")
                    if len(stack) < 2: raise XTemplateError(f"unexpected endwhile")
                    term = not loopactive or brkcnt == 1
                    _, _, expr, pos = stackend
                    if not term:
                        if bool(evaluate(expr)):
                            stream.seek(pos)
                            stackend[0:2] = [True, True]
                        else: term = True
                    if term: stack.pop()
                    brkcnt = 0 if brkcnt <= 2 else brkcnt - 2

                elif not anyactive:  # no more stack-oriented flow control checks
                    continue 

                elif kw == "break":
                    _, _, expr = line.partition(" if ")
                    brkcnt = 1 if not expr or bool(evaluate(expr)) else 0

                elif kw == "continue":
                    _, _, expr = line.partition(" if ")
                    brkcnt = 2 if not expr or bool(evaluate(expr)) else 0

                elif kw == "set":
                    var, _, expr = rest.partition("=")
                    _locals[var.strip()] = evaluate(expr)

                elif kw == "include":
                    expr, _, args = rest.partition(" with ")
                    incpath = str(evaluate(expr))
                    sub_locals = _locals.copy()
                    if args: # parse arguments arg=val, arg=val
                        args = f"dict({args})"
                        args = evaluate(args)
                        sub_locals.update(args)
                    yield from self._render(incpath, lines_left, sub_locals)

                elif kw == "emit":
                    with self.open_with(str(evaluate(rest))) as f:
                        while data := f.readline():
                            yield data.decode() if hasattr(data,"decode") else data

                elif kw == "exit": 
                    _, _, expr = line.partition(" if ")
                    if not (expr or bool(evaluate(expr))): return

                elif kw == "raise":
                    raise XTemplateError("template raised an error: "+str(evaluate(rest)))
 
                elif kw == "args":
                    for arg in [a.strip() for a in rest.split(',')]:
                        if not arg in _locals: raise XTemplateError(f"argument '{arg}' missing")

                else: raise XTemplateError(f"unknown keyword '{kw}'")

        except Exception as e:
            opos, l = stream.tell(), 0 
            stream.seek(0)
            while stream.tell() < opos: # find line number 
                stream.readline()
                l += 1
            with io.StringIO() as str_io:
                sys.print_exception(e, str_io)
                e = f"\nXTemplate error:\n  File {fullpath}, line {l}:\n  {line}\n" + str_io.getvalue()
                if self.throw: raise RuntimeError(e)
                else: yield e

        finally:
            stream.close()

    def render(self, path, **kwargs):
        buf, l = [], 0
        for line in self._render(path, self.max_lines, kwargs):
            buf.append(line)
            l += len(line)
            if l >= self.chunk_size:
                o = "".join(buf); buf.clear(); yield o # less ram used this way
                l = 0
        if buf: 
          o = "".join(buf); buf.clear(); yield o
