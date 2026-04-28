# XTemplate

Shae M Puckett 2026

MIT license

A lightweight, streaming template engine for MicroPython. Designed for memory-constrained devices that need to serve templated HTML (or any text) without loading entire files into RAM.

---

## Table of Contents

- [Overview](#overview)
- [Design Approach](#design-approach)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Template Syntax](#template-syntax)
  - [Expressions](#expressions)
  - [Comments](#comments)
  - [Variables — `set`](#variables--set)
  - [Conditionals — `if / elif / else / endif`](#conditionals--if--elif--else--endif)
  - [For Loops — `for / endfor`](#for-loops--for--endfor)
  - [While Loops — `while / endwhile`](#while-loops--while--endwhile)
  - [Loop Control — `break / continue`](#loop-control--break--continue)
  - [Includes — `include`](#includes--include)
  - [Emit — `emit`](#emit)
  - [Required Arguments — `args`](#required-arguments--args)
  - [Early Exit — `exit`](#early-exit--exit)
  - [Raise — `raise`](#raise)
- [The XTemplate Class](#the-xtemplate-class)
  - [Constructor Parameters](#constructor-parameters)
  - [render()](#render)
- [Security](#security)
- [Memory Usage](#memory-usage)
- [Using with a Web Server](#using-with-a-web-server)
- [Error Handling](#error-handling)
- [Limitations](#limitations)

---

## Overview

XTemplate renders text templates by streaming output in chunks rather than building the full result in memory. This makes it practical on microcontrollers — an ESP32 or RP2040 can serve a full HTML page template-by-template without ever holding the whole page in RAM.

Key properties:

- **Streaming output** — yields chunks as it renders, never builds the full document in memory
- **File-based templates** — reads from the filesystem line by line using `seek`/`tell` for loops
- **Safe expression evaluation** — expressions run in a restricted `eval` sandbox with no access to builtins like `open`, `exec`, or `import`
- **Configurable** — prefix character, chunk size, base path, and the global sandbox are all adjustable

---

## Design Approach

XTemplate trades speed for runtime size.  It doesn't cache anything.  On an ESP32 device, figure about 1ms of processing time per statement or text line with interpolation. This is advantageous for devices where an active WiFi stack may be occupying a significant portion of working memory with a large amount of churn as packets come through.  XTemplate uses barely 3K of RAM in small allocations when processing templates, even several includes deep.   If you freeze XTemplate into flash, it will have hardly any footprint at all except when you are actively templating something.

I did test speending up `eval` expression computation by turning it into cached `compile` code blocks with `exec`, but the overhead of calling exec and setting up an environment seems to be greater than just calling `eval` so it's not worth even that bare attempt.  Any truly effective caching for speed would have to take place with large blocks of code and embedded text, defeating the design goals for XTemplate.

It may be "slow" but it's asynchronous in millisecond-sized fragments, so it should not introduce substantial lag in everything else your device needs to do, while it's serving pretty HTML to your end-user.

---

## Installation

Copy `xtemplate.py` to your device. No dependencies beyond the MicroPython standard library.

```python
from xtemplate import XTemplate
```

---

## Quick Start

**`templates/hello.html`**
```
<h1>Hello, {{ name }}!</h1>
# if items
<ul>
# for item in items
  <li>{{ item }}</li>
# endfor
</ul>
# endif
```

**`main.py`**
```python
from xtemplate import XTemplate

tmpl = XTemplate(base_path="/templates/")

for chunk in tmpl.render("hello.html", name="World", items=["one", "two", "three"]):
    print(chunk, end="")
```

**Output:**
```html
<h1>Hello, World!</h1>
<ul>
  <li>one</li>
  <li>two</li>
  <li>three</li>
</ul>
```

---

## Template Syntax

Templates are plain text files. Lines that begin with `#` (the default prefix) are **statements**. All other lines are **body text** and are passed through to output — with `{{ expr }}` expressions interpolated.

### Expressions

Anywhere in body text, wrap a Python expression in `{{ }}` to have it evaluated and its result inserted:

```
<p>The answer is {{ 6 * 7 }}</p>
<p>User: {{ username.upper() }}</p>
<p>Items: {{ len(cart) }}</p>
```

Expressions have access to variables passed into `render()` and set with `# set`, plus the [safe built-ins](#security).

---

### Comments

A line beginning with `##` (prefix character plus `#`) is a comment and produces no output:

```
## This is a comment — it won't appear in the output
# set x = 42   ← this IS a statement, not a comment
```

---

### Variables — `set`

Assign or update a variable in the current scope:

```
# set count = 0
# set title = page_title + " | My Site"
# set doubled = count * 2
```

Variables set within an include are scoped to that context and do not bubble up to the enclosing template/code, though their values are available to child templates `included` within.  No other scope control is performed, including within loops.

---

### Conditionals — `if / elif / else / endif`

```
# if user
  <p>Welcome back, {{ user }}!</p>
# elif guest
  <p>Hello, guest.</p>
# else
  <p>Please log in.</p>
# endif
```

Conditions are any Python expression that evaluates to a truthy/falsy value.

> **Note:** Every `# if` must have a matching `# endif`.

---

### For Loops — `for / endfor`

Iterate over any iterable:

```
# for product in products
  <div class="product">{{ product.name }} — ${{ product.price }}</div>
# endfor
```

```
# for i in range(5)
  <p>Row {{ i }}</p>
# endfor
```

Loops support `else` to render a block when the iterable is empty:

```
# for item in cart
  <li>{{ item }}</li>
# else
  <p>Your cart is empty.</p>
# endfor
```

> **Important:** For loops use `stream.seek()` to rewind the file for each iteration. Templates must be stored on a filesystem that supports seeking (i.e., regular files — not stdin or network streams).

> **Note:** Every `# for` must have a matching `# endfor`.

> **Note:** XTemplate loops, including `for`, do not enclose (scope) variables used within them.  
---

### While Loops — `while / endwhile`

```
# set n = 1
# while n <= 5
  <p>{{ n }}</p>
  # set n = n + 1
# endwhile
```

Like `for`, `while` supports `else` (runs if the condition was false on the very first check):

```
# while queue
  Processing: {{ queue.pop(0) }}
# else
  Nothing to process.
# endwhile
```

> **Note:** Every `# while` must have a matching `# endwhile`.

---

### Loop Control — `break / continue`

Both work unconditionally or with a condition:

```
# break
# break if count > 10

# continue
# continue if item is None
```

`break` exits the nearest enclosing loop. `continue` skips to the next iteration. Conditions use the form `if <expr>` at the end of the statement — the rest of the line after ` if ` is evaluated.

---

### Includes — `include`

Insert another template file. The included file inherits the current variables and can receive additional ones:

```
# include "header.html"
# include "card.html" with title=product.name, price=product.price
```

The path is a Python expression, so it can be dynamic:

```
# include component_path
# include "partials/" + theme + "/nav.html"
```

Included templates run with a **copy** of the current locals, so any `# set` statements inside an include don't affect the parent template.

> **Memory note:** Each active `include` adds a small overhead: stream buffers, python stack, template variables. Deeply nested includes may cause issues in low memory situations.  Plan accordingly.

---

### Emit — `emit`

Output a file's raw contents with no template processing:

```
# emit "static/styles.css"
# emit asset_path
```

The path is a Python expression. The file is streamed directly to output without any expression substitution, making it efficient for static assets inlined into a response.

---

### Required Arguments — `args`

Declare that certain variables must be provided by the caller. Place this near the top of a template to catch missing data early:

```
# args title, items, user
```

If any listed variable is absent from the render context, an error is raised immediately. Useful for shared partials and includes that depend on specific inputs.

---

### Early Exit — `exit`

Stop rendering the current template (or include) immediately:

```
# exit
# exit if error_flag
```

With a condition, rendering stops only if the condition is truthy. Without a condition (or when no ` if ` clause is present), it always exits.

---

### Raise — `raise`

Emit a `XTemplateError` with a custom message — useful for asserting invariants in templates:

```
# raise "Expected a non-empty product list"
# raise "Unknown theme: " + theme
```

The message is a Python expression.

---

## The XTemplate Class

### Constructor Parameters

```python
tmpl = XTemplate(
    base_path  = "/",       # Root directory prepended to all template paths
    chunk_size = 512,       # Output buffer size in bytes before flushing a chunk
    globals    = ...,       # Sandbox globals for eval (see Security)
    open_with  = ...,       # File-open callable — replace to use custom storage
    max_lines  = 10000,     # Maximum statements processed before aborting (runaway guard)
    prefix     = "#",       # Statement line prefix character
    throw      = False      # Raise template errors as exceptions (true), or render as text inline
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_path` | `"/"` | Prepended to all paths in `render()` and `include`. Set this to your templates folder. |
| `chunk_size` | `512` | Approximate size of each yielded chunk in bytes. Tune for your network buffer or UART. |
| `globals` | safe subset | The global namespace for `eval`. Override to add or remove built-ins. |
| `open_with` | `open(path,"r")` | Callable used to open files. Replace to read from a custom VFS, compressed storage, etc. |
| `max_lines` | `10000` | Hard limit on statement evaluations. Prevents infinite loops from hanging the device. |
| `prefix` | `"#"` | Character that marks a line as a statement. Change if `#` conflicts with your content. |
| `throw` | `False` | If true, template errors are raised as exceptions; if false, errors render inline.

---

### render()

```python
for chunk in tmpl.render("page.html", title="Home", user=current_user):
    send(chunk)
```

Returns a generator that yields string chunks. Pass keyword arguments to make variables available in the template. The template file is looked up as `base_path + path`.

Call `render()` once and iterate — don't materialise the whole thing with `"".join(...)` unless you know it fits in RAM.

---

## Security

Expressions are evaluated with `eval()` in a restricted sandbox. The available built-ins are:

| Category | Functions |
|----------|-----------|
| Type coercion | `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `set` |
| Iteration | `range`, `enumerate`, `zip`, `len`, `sorted`, `reversed`, `map`, `filter`, `min`, `max`, `sum`, `any`, `all` |
| Strings | `repr`, `chr`, `ord` |
| Misc | `round`, `abs`, `isinstance`, `print` |

`open`, `exec`, `eval`, `__import__`, `compile`, and all other potentially dangerous built-ins are excluded by default.

Variables passed into `render()` are accessible in expressions. Be careful about passing raw user input as a variable value — while the sandbox prevents code injection through expressions, data you pass in is still your data.

To extend the sandbox — for example, to add `json` or a helper function — pass a modified `globals` dict:

```python
import json

my_globals = dict(xtemplate._safe_globals)  # copy the default
my_globals["__builtins__"]["json_dumps"] = json.dumps

tmpl = XTemplate(globals=my_globals)
```

---

## Memory Usage

XTemplate is designed to keep its memory footprint predictable. At any point during rendering, it holds approximately:

| What | Approximate RAM |
|------|-----------------|
| Engine base overhead | ~2 KB |
| Output buffer | `chunk_size` bytes (default 512 B) |
| Each active `include` level | 0.25 - 0.5 KB approx |

These figures can increase depending on:

- **Line length** — very long body lines are held as strings during processing
- **Expression results** — complex `{{ }}` expressions may produce large strings before yielding
- **Include depth** — each nested include adds another stack, though not another chunk buffer

**Recommendations for tight memory:**

- Keep `chunk_size` small (128–256 bytes) if RAM is the bottleneck; increase it if you're tuning for throughput.
- Break large templates into sections using `emit` for static parts — `emit` streams without any parsing overhead.
- Set a realistic `max_lines` to guard against runaway loops.
- Render directly into a socket send buffer rather than accumulating chunks.

---

## Using with a Web Server

XTemplate pairs naturally with [`MicroPython asyncio`](https://docs.micropython.org/en/latest/library/asyncio.html) servers. Yield each chunk straight into the socket writer:

```python
import asyncio
from xtemplate import XTemplate

tmpl = XTemplate(base_path="/templates/")

async def handle(reader, writer):
    # Read request (simplified)
    await reader.readline()

    writer.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n")

    for chunk in tmpl.render("index.html", title="Hello"):
        writer.write(chunk.encode())
        await writer.drain()   # yield to event loop between chunks

    await writer.aclose()

asyncio.run(asyncio.start_server(handle, "0.0.0.0", 80))
```

No intermediate buffering. Chunks go to the network as soon as the template produces them.

---

## Error Handling

If the throw flag is false, when an error occurs during rendering, XTemplate catches the exception and **yields the error information as output text** rather than propagating the exception. 

The error output includes:

- The exception traceback
- The full path of the template file, and line number where the error occurred
- The raw line that caused it

Errors within nested templates will show multiple tracebacks including all template information.

If throw is true, rendering ends immediately, and the exception is re-raised with the above information appended.


**Common errors and causes:**

| Error | Cause |
|-------|-------|
| `SyntaxError: unexpected endif` | `# endif` with no matching `# if` |
| `SyntaxError: expected endwhile not endif` | Mismatched block closing keyword |
| `RuntimeError: runaway template expansion` | `max_lines` exceeded — usually an infinite loop |
| `RuntimeError: argument '...' missing` | `# args` declaration not satisfied by caller |

---

## Limitations

- **Seek required for loops.** `for` and `while` loops rewind the file stream using `seek()`. Template files must be on a seekable filesystem. Streaming templates over a network or reading from stdin is not supported for templates that contain loops.
- **Single-file templates.** Each template is one file; there is no block inheritance or `extends` mechanism. Composition is done through `include`.
- **No expression assignment.** `{{ x = 1 }}` is not valid — use `# set x = 1` for assignments.
- **No multi-line statements.** Each `#` statement must fit on a single line.
