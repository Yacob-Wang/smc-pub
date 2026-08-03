# 06-Foundation/Build-System/Soong · 03 · Blueprint：Soong 的中间表示与解析

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 改源码工程师 · 想理解 Soong 内部的人
>
> **强依赖**：[01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) · [02 Android.bp 语法精要](02-Android.bp语法精要.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Blueprint（Soong 的中间表示层）讲清楚——Android.bp 怎么从配置文件变成 Go AST，编译期怎么校验 module，错误信息怎么精确到行号
- **不是**：不复述 [02 §1-3 9 大 module 类型](02-Android.bp语法精要.md)；不复述 [04 Soong 整体架构](04-Soong架构：plugin.provider.mutator.generator.md)
- **承接自**：[02 §2 srcs / include_dirs](02-Android.bp语法精要.md)（"为什么拼错属性名能精确报错"答案在 Blueprint）
- **衔接去**：[04 Soong 架构](04-Soong架构：plugin.provider.mutator.generator.md) / [05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章用 4 阶段解析流 Android.bp → token → AST → module | 教科书式拆分最清晰 |
| 2 | 第 6 章用真实 build/blueprint/parser.go 代码走读 | 不用 toy 例子 |
| 3 | 第 7 章错误处理单独成节 | 编译期错误体验是 Blueprint 的核心优势 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Blueprint = Android.bp 的"前端编译器"——把 JSON-like 配置转成 Go AST，再交给 Soong 做 module 验证和 provider/mutator 计算。**

读懂 Blueprint = 改 module 时知道"错在第 1 步（lex）还是第 2 步（parse）还是第 3 步（type check）"——5 秒定位编译错误。

---

## 1. Blueprint 在 Soong 中的位置

```
AOSP 编译系统全景（再放大看）
═══════════════════════════════════════════════════════════════════

vendor 写              Soong 内部                    执行
─────────             ──────────                    ────
                     ┌─────────────────────┐
Android.bp ────────→ │   Blueprint         │ → Go struct
(JSON-like)          │   (前端)            │   (module 列表)
                     └─────────┬───────────┘
                               │ Go struct
                               ▼
                     ┌─────────────────────┐
                     │   Soong             │
                     │   (中端)            │ → variant / provider
                     │  - Type check       │   / mutator
                     │  - Mutator          │
                     │  - Provider         │
                     └─────────┬───────────┘
                               │ module + variant
                               ▼
                     ┌─────────────────────┐
                     │   Generator         │ → build.ninja
                     └─────────┬───────────┘
                               │
                               ▼
                     [Ninja 执行]
```

**Blueprint 的位置**：**第 1 阶段**，把配置文件变成结构化数据。

---

## 2. 4 阶段解析流

### 2.1 完整流程

```
Android.bp
   ↓
[1] Lexer (词法分析)
   ↓
Token 流
   ↓
[2] Parser (语法分析)
   ↓
AST (Abstract Syntax Tree)
   ↓
[3] Type check (类型检查)
   ↓
Module 列表（已验证）
   ↓
[4] 交给 Soong
   ↓
mutator / provider / generator
```

### 2.2 每阶段产物

| 阶段 | 产物 | 谁实现 | 失败时表现 |
|:-----|:-----|:------|:---------|
| 1. Lexer | Token | `build/blueprint/parser/lexer.go` | "unrecognized character" |
| 2. Parser | AST | `build/blueprint/parser/parser.go` | "expected `}`" |
| 3. Type check | Module 列表 | `build/soong/android/...go` | "no such property" |
| 4. Soong | variant / build.ninja | `build/soong/cc/...go` | "no rule to make target" |

**关键洞察**：3 个阶段的错误**精确到不同层级**：
- Lexer 错：字符错（不可见字符 / 中文标点）
- Parser 错：语法错（少 `}` / 多 `,`）
- Type 错：类型错（属性名拼错 / 类型不匹配）

---

## 3. 阶段 1：Lexer（词法分析）

### 3.1 真实 Lexer 入口

`build/blueprint/parser/lexer.go`：

```go
// Lexer 把字符串切成 Token
type Lexer struct {
    text   string
    pos    int
    tokens []Token
}

type Token struct {
    Type  TokenType
    Value string
    Pos   Position  // 精确位置
}

type TokenType int

const (
    IDENT TokenType = iota
    NUMBER
    STRING
    LBRACE     // {
    RBRACE     // }
    LBRACKET   // [
    RBRACKET   // ]
    COMMA
    EQUALS
    EOF
)
```

### 3.2 Android.bp 真实 Lex 输出

```python
// 输入
android_app {
    name: "MyApp",
    srcs: ["src/*.java"],
}
```

**Lexer 输出**（Token 列表）：

```
[0] IDENT     "android_app"  pos=(1,1)
[1] LBRACE    "{"            pos=(1,12)
[2] IDENT     "name"         pos=(2,5)
[3] COLON     ":"            pos=(2,9)
[4] STRING    "MyApp"        pos=(2,11)
[5] COMMA     ","            pos=(2,17)
[6] IDENT     "srcs"         pos=(3,5)
[7] COLON     ":"            pos=(3,9)
[8] LBRACKET  "["            pos=(3,11)
[9] STRING    "src/*.java"   pos=(3,12)
[10] RBRACKET "]"            pos=(3,23)
[11] COMMA    ","            pos=(3,24)
[12] RBRACE   "}"            pos=(4,1)
[13] EOF      ""             pos=(4,2)
```

**关键**：每个 Token 都有 `Position`（行 + 列），错误信息能精确到行号。

### 3.3 Lexer 常见 3 个错

| 错 | 真实报错 | 根因 |
|:--|:--------|:-----|
| 不可见字符 | `unrecognized character '\u3000'` | 用了中文空格 |
| 未闭合字符串 | `unterminated string constant` | 少 `"` |
| 行尾逗号 | `comma without preceding expression` | 用了 `,` 结尾 |

---

## 4. 阶段 2：Parser（语法分析）

### 4.1 Parser 真实实现

`build/blueprint/parser/parser.go`（简化）：

```go
// parser 用递归下降
type Parser struct {
    lexer  *Lexer
    cur    Token  // 当前 Token
    peek   Token  // 下一个 Token
}

func (p *Parser) parseModule() (*Module, error) {
    // android_app { ... }
    name := p.cur.Value  // module type (android_app)
    p.consume(IDENT)
    p.consume(LBRACE)
    
    mod := &Module{Type: name}
    
    for p.cur.Type != RBRACE {
        // name: value
        propName := p.cur.Value
        p.consume(IDENT)
        p.consume(COLON)
        
        propValue := p.parseValue()  // 解析 value
        p.consume(COMMA)  // 可选
        
        mod.Properties[propName] = propValue
    }
    p.consume(RBRACE)
    
    return mod, nil
}
```

### 4.2 AST 结构

**Module 列表**（Go struct）：

```go
type Module struct {
    Type        string
    Name        string
    Properties  map[string]interface{}
    Position    Position  // module 起始位置
    Comments    []string
}

type File struct {
    Modules []*Module
}
```

### 4.3 Parser 常见 4 个错

| 错 | 真实报错 | 根因 |
|:--|:--------|:-----|
| 少 `}` | `unexpected token, expected }` | 嵌套少关 |
| 多 `,` | `unexpected token ,` | 多了 `,` |
| 属性无值 | `expected value after :` | 漏 value |
| 未关闭 list | `expected ]` | 少 `]` |

---

## 5. 阶段 3：Type check + Builder

### 5.1 Soong 怎么 type check

Soong 把 AST 交给 Go struct：

```go
// build/soong/android/androidmk.go
type AndroidModuleBase struct {
    ModuleBase
    Properties struct {
        Name        string
        Srcs        []string
        ResourceDirs []string
        // ...
    }
}

func (m *AndroidModuleBase) properties() []string {
    // 通过 reflect 拿所有 property
    return []string{"Name", "Srcs", "ResourceDirs", ...}
}
```

**Type check 做的事**：
1. 从 AST 读属性名
2. 查 Go struct 是否有这个 property
3. 没有 → 报错（精确到行号）
4. 有 → 转 Go 类型（string / []string / struct）
5. type 转换失败 → 报错（精确到行号）

### 5.2 真实 type check 报错

```bash
# 错误 1：属性名拼错
$ m myapp
error: unknown property "src" (did you mean "srcs"?)
  at packages/apps/MyApp/Android.bp:3:5

# 错误 2：值类型错
$ m myapp
error: property "srcs" expects []string, got string
  at packages/apps/MyApp/Android.bp:3:11

# 错误 3：required 属性缺失
$ m myapp
error: "name" is required
  at packages/apps/MyApp/Android.bp:1:1
```

**所有错误都精确到行号**——这是 Blueprint + Soong 的核心优势（vs Makefile 时代报错完全模糊）。

### 5.3 Builder 全局 module 表

```go
// build/soong/android/builder.go
type BuilderContext struct {
    modules map[string]Module  // name → module
    ctx     *android.Context
}

func (b *BuilderContext) AddModule(m Module) {
    name := m.Name()
    if existing, ok := b.modules[name]; ok {
        // 重名！报错
        panic(fmt.Errorf("module %s already defined at %s", name, existing.Position))
    }
    b.modules[name] = m
}
```

**关键不变量**：
- module name 全局唯一
- 同名 → 编译期 panic
- panic 信息**包含两个冲突位置**

---

## 6. 真实代码走读：build/blueprint/parser.go

### 6.1 关键函数

```go
// build/blueprint/parser/parser.go
const ParserName = "Blueprints"

func Parse(filename string, r io.Reader) (file *File, errs []error) {
    // 1. 读文件
    text, err := ioutil.ReadAll(r)
    if err != nil {
        return nil, []error{err}
    }
    
    // 2. Lexer
    lexer := NewLexer(filename, string(text))
    tokens, err := lexer.Lex()
    if err != nil {
        return nil, []error{err}
    }
    
    // 3. Parser
    parser := NewParser(filename, tokens)
    file, errs = parser.Parse()
    if errs != nil {
        return nil, errs
    }
    
    return file, nil
}
```

### 6.2 真实 parseValue 递归

```go
// 解析 value（支持 string / list / map / bool / int）
func (p *Parser) parseValue() (interface{}, error) {
    switch p.cur.Type {
    case STRING:
        v := p.cur.Value
        p.advance()
        return v, nil
    case NUMBER:
        v, _ := strconv.Atoi(p.cur.Value)
        p.advance()
        return v, nil
    case LBRACKET:
        return p.parseList()
    case LBRACE:
        return p.parseMap()
    case IDENT:
        // bool: true / false
        // 标识符: default
        v := p.cur.Value
        p.advance()
        return v, nil
    }
    return nil, fmt.Errorf("unexpected token %s at %s", p.cur, p.cur.Pos)
}
```

### 6.3 parseList 实现

```go
func (p *Parser) parseList() ([]interface{}, error) {
    p.consume(LBRACKET)
    var list []interface{}
    for p.cur.Type != RBRACKET {
        v, err := p.parseValue()
        if err != nil {
            return nil, err
        }
        list = append(list, v)
        if p.cur.Type == COMMA {
            p.advance()
        } else {
            break
        }
    }
    p.consume(RBRACKET)
    return list, nil
}
```

**关键点**：
- `parseList` 递归调 `parseValue`
- `parseValue` 递归调 `parseList` / `parseMap`
- 任意嵌套结构都能解析

---

## 7. 错误处理与位置追踪

### 7.1 Position 精确追踪

```go
// build/blueprint/parser/position.go
type Position struct {
    Filename string
    Line     int  // 1-based
    Column   int  // 1-based
}

func (p Position) String() string {
    return fmt.Sprintf("%s:%d:%d", p.Filename, p.Line, p.Column)
}
```

**真实错误信息**：

```
error: unknown property "src"
  at packages/apps/MyApp/Android.bp:3:5
  
# ↑ "packages/apps/MyApp/Android.bp" 是 filename
# ↑ "3" 是行号
# ↑ "5" 是列号
```

**直接 vim + :3 → 跳到错位置**——是 5 秒修复的关键。

### 7.2 错误聚合

```go
// build/blueprint/parser/parser.go
type Parser struct {
    errs []error  // 收集所有错误，不中途退出
}

func (p *Parser) Parse() (*File, []error) {
    for p.cur.Type != EOF {
        if mod, err := p.parseModule(); err != nil {
            p.errs = append(p.errs, err)
            // 不 return，继续解析下一个 module
        } else {
            file.Modules = append(file.Modules, mod)
        }
    }
    if len(p.errs) > 0 {
        return nil, p.errs
    }
    return file, nil
}
```

**关键设计**：
- 一次编译**报所有错**（不修一个又出一个）
- 这是 Blueprint 的工程哲学

### 7.3 真实 vs Makefile 时代错误对比

**Makefile 时代**：
```
make: *** No rule to make target 'foo.o', needed by 'libfoo.so'.  Stop.
# 不知道哪个 .c 生成的 .o
# 不知道在哪个 Makefile
```

**Blueprint + Soong 时代**：
```
error: "src" is not a property of android_app
  at packages/apps/MyApp/Android.bp:3:5
  
# 精确到行 + 列
# 提示正确的属性名（srcs）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) | 历史背景 |
| [02 Android.bp 语法精要](02-Android.bp语法精要.md) | 配置写法 |
| [04 Soong 架构](04-Soong架构：plugin.provider.mutator.generator.md) | 下篇讲 Soong 怎么用 Blueprint 产出的 module |
| [05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md) | M4 |
| [07 常见编译错误](07-常见编译错误速查.md) | M4 |
| [Build-System/04_Build_Configuration_And_Options](../04_Build_Configuration_And_Options.md) | BoardConfig.mk 跟 Android.bp 配合 |
| [06-Foundation/SELinux/02](../../05-安全基础（SELinux%20·%20AVB）/SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md) | SELinux 编译也走 Soong + Blueprint |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[04 Soong 架构：plugin / provider / mutator / generator](04-Soong架构：plugin.provider.mutator.generator.md) 讲清：
- Soong 怎么从 Blueprint 的 module 列表算出 variant
- provider / mutator / generator 的 Go 接口
- 真实走读：cc_library 的 mutator 链
- Android.bp 的 module 怎么变出 arm64-v8a / armeabi-v7a / x86_64 等 variant

### 9.2 看完本文的自检

- [ ] 能说 Blueprint 在 Soong 全景中的位置
- [ ] 能说 Android.bp → token → AST → module 的 4 阶段解析
- [ ] 能从 1 个编译错定位到 Lexer / Parser / Type check 哪个阶段
- [ ] 知道 build/blueprint/parser.go 关键函数
- [ ] 能解释为什么 Blueprint 错误能精确到行号

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
