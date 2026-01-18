import os
import argparse
from tree_sitter import Language, Parser
import platform 
import re 
import sys
import inspect
from collections import defaultdict

# Added common C++ build output folders to exclusion list
excluded_dir_names = ['.git', 'obj', 'bin', 'venv', '.vs', 'node_modules', 'tmp', 'temp', 'tmp_project_files', 'x64', 'Debug', 'Release', 'Profiling']


def load_pip_languages():
    """
    Loads tree-sitter languages from installed pip packages.
    Returns PyCapsule objects.
    """
    CSHARP_LANG_CAPSULE = None
    JAVASCRIPT_LANG_CAPSULE = None
    HTML_LANG_CAPSULE = None
    PYTHON_LANG_CAPSULE = None
    CPP_LANG_CAPSULE = None

    print("Attempting to load languages from installed pip packages...")
    print(f"Python sys.path: {sys.path}") 

    try:
        from tree_sitter_c_sharp import language as ts_csharp_lang_func 
        CSHARP_LANG_CAPSULE = ts_csharp_lang_func() 
        print("Successfully loaded C# language capsule.")
    except ImportError:
        print("Warning: tree-sitter-c-sharp package not found. C# parsing will be unavailable.")
    except Exception as e:
        print(f"Error loading C# language from package: {e}")

    try:
        from tree_sitter_javascript import language as ts_javascript_lang_func
        JAVASCRIPT_LANG_CAPSULE = ts_javascript_lang_func()
        print("Successfully loaded JavaScript language capsule.")
    except ImportError:
        print("Warning: tree-sitter-javascript package not found. JavaScript parsing will be unavailable.")
    except Exception as e:
        print(f"Error loading JavaScript language from package: {e}")

    try:
        from tree_sitter_html import language as ts_html_lang_func
        HTML_LANG_CAPSULE = ts_html_lang_func()
        print("Successfully loaded HTML language capsule.")
    except ImportError:
        print("Warning: tree-sitter-html package not found. HTML/CSHTML parsing will be unavailable.")
    except Exception as e:
        print(f"Error loading HTML language from package: {e}")

    try:
        from tree_sitter_python import language as ts_python_lang_func
        PYTHON_LANG_CAPSULE = ts_python_lang_func()
        print("Successfully loaded Python language capsule.")
    except ImportError:
        print("Warning: tree-sitter-python package not found. Python parsing will be unavailable.")
    except Exception as e:
        print(f"Error loading Python language from package: {e}")

    try:
        from tree_sitter_cpp import language as ts_cpp_lang_func
        CPP_LANG_CAPSULE = ts_cpp_lang_func()
        print("Successfully loaded C++ language capsule.")
    except ImportError:
        print("Warning: tree-sitter-cpp package not found. C/C++ parsing will be unavailable.")
    except Exception as e:
        print(f"Error loading C++ language from package: {e}")


    if not any([CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE, CPP_LANG_CAPSULE]):
        print("Error: No tree-sitter language packages could be loaded.")
        print("Please ensure you have installed the necessary packages, e.g.:")
        print("  pip install tree-sitter-c-sharp tree-sitter-javascript tree-sitter-html tree-sitter-python tree-sitter-cpp")
        return None

    return CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE, CPP_LANG_CAPSULE


# --- Helper to get text from a node ---
def get_node_text(node, source_bytes, default=""):
    """Safely gets text from a node, returning default if node is None."""
    if not node:
        return default
    return source_bytes[node.start_byte:node.end_byte].decode("utf8", errors="replace")

# --- C# Analysis ---
def analyze_csharp_node(node, source_bytes, summary, usings_list, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == "compilation_unit":
        for child_idx in range(node.child_count):
            analyze_csharp_node(node.child(child_idx), source_bytes, summary, usings_list, indent_level)

    elif node_type == "using_directive":
        # (Using logic remains same, just compacting logic here for brevity in the snippet)
        alias_node = node.child_by_field_name("alias") 
        name_node = node.child_by_field_name("name")  
        static_node = node.child_by_field_name("static")
        
        using_parts = []
        if static_node: using_parts.append("static")
        if alias_node:
            alias_identifier = alias_node.child_by_field_name("name") 
            alias_text = get_node_text(alias_identifier, source_bytes).strip()
            if alias_text: using_parts.append(f"{alias_text} =")

        namespace_str = get_node_text(name_node, source_bytes).strip()
        if namespace_str: using_parts.append(namespace_str)
        
        final_using_text = " ".join(filter(None, using_parts))
        if final_using_text:
            usings_list.append(final_using_text)
        else:
            # Fallback for complex usings
            raw = get_node_text(node, source_bytes).strip()
            raw = re.sub(r'^using\s+', '', raw).rstrip(';')
            if raw: usings_list.append(raw)

    elif node_type == "namespace_declaration":
        name_node = node.child_by_field_name("name")
        namespace_name = get_node_text(name_node, source_bytes, default="[UnknownNamespace]")
        summary.append(f"{indent}namespace {namespace_name}")
        body_node = node.child_by_field_name("body")
        if body_node:
            for child_idx in range(body_node.child_count):
                analyze_csharp_node(body_node.child(child_idx), source_bytes, summary, usings_list, indent_level + 1)

    elif node_type in ["class_declaration", "struct_declaration", "interface_declaration", "enum_declaration", "record_declaration"]:
        name_node = node.child_by_field_name("name")
        type_params_node = node.child_by_field_name("type_parameters")
        name_str = get_node_text(name_node, source_bytes, default="[UnnamedType]")
        if type_params_node:
            name_str += get_node_text(type_params_node, source_bytes)

        keyword = node_type.split('_')[0] # class, struct, interface...
        summary.append(f"{indent}{keyword} {name_str}")
        
        body_node = node.child_by_field_name("body")
        if body_node:
            for child_idx in range(body_node.child_count):
                analyze_csharp_node(body_node.child(child_idx), source_bytes, summary, usings_list, indent_level + 1)

    elif node_type == "method_declaration":
        return_type_node = node.child_by_field_name("type")
        name_node = node.child_by_field_name("name")
        explicit_specifier = node.child_by_field_name("explicit_interface_specifier")
        params_node = node.child_by_field_name("parameters")

        method_name = ""
        if name_node:
            method_name = get_node_text(name_node, source_bytes)
        elif explicit_specifier:
            method_name = get_node_text(explicit_specifier, source_bytes)
        else:
            # Fallback scan
            found_id = next((c for c in node.children if c.type == 'identifier'), None)
            method_name = get_node_text(found_id, source_bytes) if found_id else "[UnknownMethod]"

        params_text = get_node_text(params_node, source_bytes, default="()")
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())

        return_type_text = get_node_text(return_type_node, source_bytes).strip()
        if not return_type_text:
            return_type_text = "void" # Default to void if parsing fails or it's void

        summary.append(f"{indent}{return_type_text} {method_name}{params_text}")

    elif node_type == "constructor_declaration":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name_text = get_node_text(name_node, source_bytes, default="[Constructor]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        summary.append(f"{indent}{name_text}{params_text}")

    elif node_type == "destructor_declaration":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name_text = get_node_text(name_node, source_bytes, default="[Destructor]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        summary.append(f"{indent}~{name_text}{params_text}")

    elif node_type == "field_declaration":
        # Robust Logic from previous step
        type_node = node.child_by_field_name("type")
        declarators = []

        # 1. Direct children
        for child in node.children:
            if child.type == "variable_declarator":
                declarators.append(child)
        
        # 2. Nested variable_declaration (for attributes/modern grammar)
        if not declarators:
            for child in node.children:
                if child.type == "variable_declaration":
                    if not type_node: type_node = child.child_by_field_name("type")
                    for sub_child in child.children:
                        if sub_child.type == "variable_declarator":
                            declarators.append(sub_child)

        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>").strip()

        if declarators:
            for decl in declarators:
                name_node = decl.child_by_field_name("name")
                name_text = get_node_text(name_node, source_bytes, default="[UnnamedField]")
                # Format: "Type Name;"
                summary.append(f"{indent}{type_text} {name_text};")
        else:
            summary.append(f"{indent}{type_text} [ComplexField];")

    elif node_type == "property_declaration":
        type_node = node.child_by_field_name("type")
        name_node = node.child_by_field_name("name")
        explicit_specifier = node.child_by_field_name("explicit_interface_specifier")

        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>")
        name_text = ""
        if name_node:
            name_text = get_node_text(name_node, source_bytes)
        elif explicit_specifier:
            name_text = get_node_text(explicit_specifier, source_bytes)
        else:
            name_text = "[UnnamedProperty]"
        
        # Format: "Type Name { get; }" to distinguish from field
        summary.append(f"{indent}{type_text} {name_text} {{ get; }}")

    elif node_type == "event_field_declaration": 
        type_node = node.child_by_field_name("type")
        declarators = []
        for child in node.children:
             if child.type == "variable_declarator": declarators.append(child)
        if not declarators:
             for child in node.children:
                 if child.type == "variable_declaration":
                     if not type_node: type_node = child.child_by_field_name("type")
                     for sub_child in child.children:
                         if sub_child.type == "variable_declarator": declarators.append(sub_child)

        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>").strip()

        if declarators:
            for decl in declarators:
                name_node = decl.child_by_field_name("name")
                name_text = get_node_text(name_node, source_bytes, default="[UnnamedEvent]")
                summary.append(f"{indent}event {type_text} {name_text};")
        else:
            summary.append(f"{indent}event {type_text} [ComplexEvent];")

    elif node_type == "delegate_declaration":
        return_type_node = node.child_by_field_name("return_type")
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        
        ret_text = get_node_text(return_type_node, source_bytes, default="void")
        name_text = get_node_text(name_node, source_bytes, default="[Delegate]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        
        summary.append(f"{indent}delegate {ret_text} {name_text}{params_text};")


def process_csharp(file_path, parser, summary):
    file_summary = []
    usings_list = []
    if not parser:
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_csharp_node(tree.root_node, source_bytes, file_summary, usings_list)
        
        if file_summary or usings_list:
            summary.append(f"\n-- FILE: {file_path} (C#) --")
            if usings_list:
                summary.append(f"  USINGS: {', '.join(sorted(list(set(usings_list))))}")
            summary.extend(file_summary)
    except Exception as e:
        summary.append(f"\n-- FILE: {file_path} (C#) --")
        summary.append(f"  Error processing {file_path}: {e}")

# --- JavaScript Analysis ---
def analyze_javascript_node(node, source_bytes, summary, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == "program":
        for child_idx in range(node.child_count):
            analyze_javascript_node(node.child(child_idx), source_bytes, summary, indent_level)
    elif node_type == "function_declaration":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        func_name = get_node_text(name_node, source_bytes, default="[anonymous_function]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        summary.append(f"{indent}FUNC: {func_name}{params_text}") 
    elif node_type == "class_declaration":
        name_node = node.child_by_field_name("name")
        class_name = get_node_text(name_node, source_bytes, default="[UnnamedClass]")
        summary.append(f"{indent}CLASS: {class_name}")
        body_node = node.child_by_field_name("body")
        if body_node:
            for child_idx in range(body_node.child_count):
                 method_node = body_node.child(child_idx)
                 if method_node.type == "method_definition": 
                    analyze_javascript_node(method_node, source_bytes, summary, indent_level + 1)
    elif node_type == "method_definition":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        kind_node = node.child_by_field_name("kind") 
        
        method_name = get_node_text(name_node, source_bytes, default="[unnamed_method]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        kind_text = get_node_text(kind_node, source_bytes) 

        prefix = "METHOD"
        if method_name == "constructor":
            prefix = "CONSTRUCTOR"
        elif kind_text == "get": prefix = "GETTER"
        elif kind_text == "set": prefix = "SETTER"
        summary.append(f"{indent}{prefix}: {method_name}{params_text}")

    elif node_type == "lexical_declaration" or node_type == "variable_declaration":
        kind_token_node = node.child(0) 
        kind_token_text = get_node_text(kind_token_node, source_bytes).upper() if kind_token_node else "VAR"

        for child_idx in range(node.child_count): 
            child_decl = node.child(child_idx)
            if child_decl.type == "variable_declarator":
                name_node = child_decl.child_by_field_name("name")
                name_text = get_node_text(name_node, source_bytes, default="[unnamed_variable]")
                value_node = child_decl.child_by_field_name("value")
                if value_node and value_node.type == "arrow_function":
                    arrow_params_node = value_node.child_by_field_name("parameters")
                    arrow_params_text = get_node_text(arrow_params_node, source_bytes, default="()")
                    summary.append(f"{indent}ARROW_FUNCTION ({kind_token_text}): {name_text}{arrow_params_text}")
                else:
                    summary.append(f"{indent}VARIABLE ({kind_token_text}): {name_text}")

def process_javascript(file_path, parser, summary):
    file_summary = []
    if not parser:
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_javascript_node(tree.root_node, source_bytes, file_summary)
        if file_summary:
            summary.append(f"\n-- FILE: {file_path} (JavaScript) --")
            summary.extend(file_summary)
    except Exception as e:
        summary.append(f"\n-- FILE: {file_path} (JavaScript) --")
        summary.append(f"  Error processing {file_path}: {e}")

# --- CSHTML Analysis (Simplified) ---
def analyze_cshtml_node(node, source_bytes, summary, js_parser, cs_parser, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == "script_element":
        summary.append(f"{indent}SCRIPT BLOCK:")
        script_content_node = None
        if node.child_count > 2 and node.child(1).type == "raw_text": 
             script_content_node = node.child(1)
        elif node.child_by_field_name("text"): 
            script_content_node = node.child_by_field_name("text")

        if script_content_node and js_parser:
            script_text_bytes = get_node_text(script_content_node, source_bytes).encode('utf8')
            if script_text_bytes.strip(): 
                try:
                    js_tree = js_parser.parse(script_text_bytes)
                    analyze_javascript_node(js_tree.root_node, script_text_bytes, summary, indent_level + 1)
                except Exception as e:
                    summary.append(f"{indent}  Error parsing JS in script block: {e}")
        elif not js_parser and script_content_node and get_node_text(script_content_node, source_bytes).strip():
             summary.append(f"{indent}  JavaScript parser not available for script block.")
        return 

    if node_type == "text" or node_type == "template_content":
        text_content = get_node_text(node, source_bytes)
        if re.search(r"@(?:functions|code)\b", text_content, re.IGNORECASE):
            summary.append(f"{indent}CSHTML C# BLOCK (@functions/@code) DETECTED.")
            match = re.search(r"@(?:functions|code)\s*\{([\s\S]*?)\s*\}", text_content, re.IGNORECASE | re.DOTALL)
            if match and cs_parser:
                csharp_code_in_block = match.group(1).strip()
                if csharp_code_in_block:
                    csharp_code_bytes = csharp_code_in_block.encode('utf-8')
                    try:
                        cs_tree = cs_parser.parse(csharp_code_bytes)
                        analyze_csharp_node(cs_tree.root_node, csharp_code_bytes, summary, [], indent_level + 1)
                    except Exception as e:
                        summary.append(f"{indent}    Error parsing C# in CSHTML block: {e}")
            elif not cs_parser and match: 
                 summary.append(f"{indent}  C# parser not available for CSHTML block.")
    for child_idx in range(node.child_count):
        analyze_cshtml_node(node.child(child_idx), source_bytes, summary, js_parser, cs_parser, indent_level)


def process_cshtml(file_path, html_parser, js_parser, cs_parser, summary):
    file_summary = []
    if not html_parser:
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()

        source_text_for_directives = source_bytes.decode('utf-8', errors='ignore')
        for line_num, line in enumerate(source_text_for_directives.splitlines()):
            if line_num > 30: 
                break
            stripped_line = line.strip()
            if stripped_line.startswith("@page"):
                file_summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@model"):
                file_summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@using"): 
                file_summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@inject"):
                file_summary.append(f"  DIRECTIVE: {stripped_line}")

        tree = html_parser.parse(source_bytes)
        analyze_cshtml_node(tree.root_node, source_bytes, file_summary, js_parser, cs_parser)
        if file_summary:
            summary.append(f"\n-- FILE: {file_path} (CSHTML) --")
            summary.extend(file_summary)
    except Exception as e:
        summary.append(f"\n-- FILE: {file_path} (CSHTML) --")
        summary.append(f"  Error processing {file_path}: {e}")


def analyze_python_node(node, source_bytes, summary, imports_list, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == "module":
        for child in node.children:
            analyze_python_node(child, source_bytes, summary, imports_list, indent_level)
    
    elif node_type == "import_from_statement":
        module_name_node = node.child_by_field_name("module_name")
        module_name = get_node_text(module_name_node, source_bytes)
        
        imported_names_node = node.child_by_field_name("name")
        imported_names = get_node_text(imported_names_node, source_bytes)
        
        imports_list.append(f"from {module_name} import {imported_names}")

    elif node_type == "import_statement":
        name_node = node.child_by_field_name("name")
        module_name = get_node_text(name_node, source_bytes)
        imports_list.append(f"import {module_name}")

    elif node_type == "decorated_definition":
        for child in node.children:
            if child.type == "decorator":
                summary.append(f"{indent}DECORATOR: @{get_node_text(child.child_by_field_name('name'), source_bytes)}")
        definition_node = node.children[-1]
        analyze_python_node(definition_node, source_bytes, summary, imports_list, indent_level)

    elif node_type == "function_definition":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        func_name = get_node_text(name_node, source_bytes, "[lambda]")
        params_text = get_node_text(params_node, source_bytes, "()")
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        summary.append(f"{indent}FUNC: {func_name}{params_text}")
        
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                analyze_python_node(child, source_bytes, summary, imports_list, indent_level + 1)
    
    elif node_type == "class_definition":
        name_node = node.child_by_field_name("name")
        class_name = get_node_text(name_node, source_bytes)
        
        superclasses_node = node.child_by_field_name("superclasses")
        superclasses_text = get_node_text(superclasses_node, source_bytes, "")
        
        summary.append(f"{indent}CLASS: {class_name}{superclasses_text}")
        
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                analyze_python_node(child, source_bytes, summary, imports_list, indent_level + 1)


def process_python(file_path, parser, summary):
    """Wrapper function to process a single Python file."""
    file_summary = []
    imports_list = []
    if not parser:
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_python_node(tree.root_node, source_bytes, file_summary, imports_list)
        if file_summary or imports_list:
            summary.append(f"\n-- FILE: {file_path} (Python) --")
            if imports_list:
                summary.append(f"  IMPORTS: {', '.join(sorted(list(set(imports_list))))}")
            summary.extend(file_summary)
    except Exception as e:
        summary.append(f"\n-- FILE: {file_path} (Python) --")
        summary.append(f"  Error processing {file_path}: {e}")


def analyze_cpp_node(node, source_bytes, summary, includes_list, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == 'translation_unit':
        for child in node.children:
            analyze_cpp_node(child, source_bytes, summary, includes_list, indent_level)

    elif node_type == 'preproc_include':
        path_node = node.child_by_field_name('path')
        path_text = get_node_text(path_node, source_bytes)
        includes_list.append(path_text)
    
    elif node_type == 'namespace_definition':
        name_node = node.child_by_field_name('name')
        name = get_node_text(name_node, source_bytes)
        summary.append(f"{indent}NAMESPACE: {name}")
        body_node = node.child_by_field_name('body')
        if body_node:
            for child in body_node.children:
                analyze_cpp_node(child, source_bytes, summary, includes_list, indent_level + 1)

    elif node_type in ['class_specifier', 'struct_specifier', 'union_specifier']:
        if not node.child_by_field_name('body'):
            return

        type_keyword = node_type.split('_')[0].upper()
        name_node = node.child_by_field_name('name')
        name = get_node_text(name_node, source_bytes, default="[Anonymous]")
        summary.append(f"{indent}{type_keyword}: {name}")
        
        body_node = node.child_by_field_name('body')
        if body_node:
            for child in body_node.children:
                analyze_cpp_node(child, source_bytes, summary, includes_list, indent_level + 1)
    
    elif node_type == 'function_definition':
        type_node = node.child_by_field_name('type')
        declarator_node = node.child_by_field_name('declarator')
        
        if declarator_node:
            name_node = declarator_node.child_by_field_name('declarator')
            params_node = declarator_node.child_by_field_name('parameters')
            
            while name_node and name_node.type not in ['identifier', 'qualified_identifier', 'operator_name', 'destructor_name']:
                 name_node = name_node.child_by_field_name('declarator')

            func_name = get_node_text(name_node, source_bytes, '[unnamed_func]')
            params_text = get_node_text(params_node, source_bytes, '()')
            params_text = re.sub(r'\s*[\r\n]+\s*', ' ', params_text).strip()
            
            return_type = get_node_text(type_node, source_bytes, '').strip()
            if return_type == "void":
                return_type = "" # Omit void return type

            prefix = "FUNC"
            # Heuristic for constructor/destructor
            if not return_type:
                 if func_name.startswith("~"):
                    prefix = "DESTRUCTOR"
                 else:
                    prefix = "CONSTRUCTOR"

            full_sig = f"{return_type} {func_name}{params_text}".strip()
            summary.append(f"{indent}{prefix}: {full_sig}")

    elif node_type == 'declaration' or node_type == 'field_declaration':
        func_declarator = next((c for c in node.children if 'function_declarator' in c.type), None)
        if func_declarator:
            type_node = node.child_by_field_name('type')
            params_node = func_declarator.child_by_field_name('parameters')
            name_node = func_declarator.child_by_field_name('declarator')

            type_text = get_node_text(type_node, source_bytes).strip()
            if type_text == "void":
                type_text = "" # Omit void return type

            func_name = get_node_text(name_node, source_bytes, '[unnamed_func]')
            params_text = get_node_text(params_node, source_bytes, '()')
            params_text = re.sub(r'\s*[\r\n]+\s*', ' ', params_text).strip()

            full_sig = f"{type_text} {func_name}{params_text}".strip()
            summary.append(f"{indent}FUNC_DECL: {full_sig}")
            return

        specifier_node = next((c for c in node.children if c.type in ['class_specifier', 'struct_specifier']), None)
        if specifier_node and not specifier_node.child_by_field_name('body'):
            declaration_text = get_node_text(node, source_bytes).strip().replace('\n', ' ').replace(';', '')
            summary.append(f"{indent}FORWARD_DECL: {declaration_text}")
            return

        type_node = node.child_by_field_name('type')
        type_text = get_node_text(type_node, source_bytes, '<unknown_type>').strip()
        
        for i in range(node.child_count):
            child_node = node.child(i)
            if 'declarator' in child_node.type:
                name_node = child_node
                while name_node.child_by_field_name('declarator'):
                    name_node = name_node.child_by_field_name('declarator')
                
                name_text = get_node_text(name_node, source_bytes).strip()
                
                if name_text and name_text != type_text:
                    summary.append(f"{indent}FIELD: {type_text} {name_text}")


def process_cpp(file_path, parser, summary):
    """Wrapper function to process a single C/C++/Header file with intelligent grouping."""
    if not parser:
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()

        tree = parser.parse(source_bytes)

        file_summary_raw = []
        includes_list = []
        analyze_cpp_node(tree.root_node, source_bytes, file_summary_raw, includes_list)

        if not file_summary_raw and not includes_list:
            return

        summary.append(f"\n-- FILE: {file_path} (C/C++) --")
        if includes_list:
            summary.append(f"  INCLUDES: {', '.join(sorted(list(set(includes_list))))}")

        # This helper function groups a block of lines (like a class body)
        def format_block(lines, base_indent):
            groups = defaultdict(list)
            for line in lines:
                match = re.match(r'^\s*(?P<type>\w+):\s*(?P<text>.*)', line)
                if match:
                    groups[match.group('type')].append(match.group('text').strip())
            
            output_lines = []
            # Define a consistent order for printing member types
            type_order = ["FIELD", "CONSTRUCTOR", "DESTRUCTOR", "FUNC", "FUNC_DECL"]
            for type_key in type_order:
                if type_key in groups:
                    output_lines.append(f"{base_indent}{type_key}:")
                    for item in sorted(groups[type_key]):
                        output_lines.append(f"{base_indent}  {item}")
            # Add any other types not in the standard order
            for type_key, items in sorted(groups.items()):
                if type_key not in type_order:
                    output_lines.append(f"{base_indent}{type_key}:")
                    for item in sorted(items):
                         output_lines.append(f"{base_indent}  {item}")
            return output_lines

        # --- Main Processing ---
        final_body = []
        
        # First, handle .cpp file definitions by grouping them into classes
        class_definitions = defaultdict(list)
        other_lines = []
        for line in file_summary_raw:
            if not line.startswith(' ') and '::' in line:
                match = re.match(r'^(?P<type>\w+):\s*(?P<signature>.*)', line)
                if match:
                    sig = match.group('signature')
                    try:
                        # Split "return_type class_name::func_name(args)"
                        qualifiers, member_name = sig.rsplit('::', 1)
                        qualifiers_parts = qualifiers.split()
                        class_name = qualifiers_parts[-1]
                        return_type = " ".join(qualifiers_parts[:-1])

                        # Reconstruct the signature without the class name
                        clean_sig = f"{return_type} {member_name}".strip()
                        class_definitions[class_name].append(f"  {match.group('type')}: {clean_sig}")
                        continue
                    except ValueError:
                        # Fallback for parsing errors
                        pass
            other_lines.append(line)

        # Process the remaining lines (from headers or globals)
        i = 0
        while i < len(other_lines):
            line = other_lines[i]
            # Match top-level containers like CLASS, STRUCT, NAMESPACE
            match = re.match(r'^(?P<indent>\s*)(?P<type>CLASS|STRUCT|NAMESPACE):\s*(?P<name>.*)', line)
            if match:
                final_body.append(line)
                block_indent_len = len(match.group('indent'))
                block_body_lines = []
                # Collect all lines belonging to this block
                j = i + 1
                while j < len(other_lines):
                    next_line = other_lines[j]
                    next_line_indent_match = re.match(r'^(\s*)', next_line)
                    next_line_indent_len = len(next_line_indent_match.group(1)) if next_line_indent_match else 0
                    
                    if next_line_indent_len > block_indent_len:
                        block_body_lines.append(next_line)
                        j += 1
                    else:
                        break # End of block
                
                if block_body_lines:
                    child_indent = match.group('indent') + '  '
                    final_body.extend(format_block(block_body_lines, child_indent))
                
                i = j # Move main index past the processed block
            else:
                final_body.append(line)
                i += 1

        # Append the formatted .cpp class definitions
        for class_name, lines in sorted(class_definitions.items()):
            final_body.append(f"CLASS: {class_name}")
            final_body.extend(format_block(lines, "  "))

        summary.extend(final_body)

    except Exception as e:
        summary.append(f"\n-- FILE: {file_path} (C/C++) --")
        summary.append(f"  Error processing {file_path}: {e}")

# --- Main Processing Logic ---
def main():
    parser_args = argparse.ArgumentParser(description="Extract code structure summary from .cs, .js, .cshtml, and .py files.")
    parser_args.add_argument("--scan_directory", help="Directory to scan recursively (e.g., '.').", default=".")
    parser_args.add_argument("--output_file", help="File to write the summary to.", default="./CODE_SUMMARY.txt")
    args = parser_args.parse_args()

    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    loaded_capsules = load_pip_languages()
    if not loaded_capsules: 
        print("Failed to load any languages from pip packages. Exiting.") 
        return

    CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE, CPP_LANG_CAPSULE = loaded_capsules

    CSHARP_LANGUAGE_OBJ, JAVASCRIPT_LANGUAGE_OBJ, HTML_LANGUAGE_OBJ, PYTHON_LANGUAGE_OBJ, CPP_LANGUAGE_OBJ = None, None, None, None, None

    if CSHARP_LANG_CAPSULE:
        try:
            CSHARP_LANGUAGE_OBJ = Language(CSHARP_LANG_CAPSULE)
            print(f"Wrapped C# capsule into Language object.")
        except Exception as e:
            print(f"Error wrapping C# capsule with Language(): {e}")
    if JAVASCRIPT_LANG_CAPSULE:
        try:
            JAVASCRIPT_LANGUAGE_OBJ = Language(JAVASCRIPT_LANG_CAPSULE)
            print(f"Wrapped JavaScript capsule into Language object.")
        except Exception as e:
            print(f"Error wrapping JavaScript capsule with Language(): {e}")
    if HTML_LANG_CAPSULE:
        try:
            HTML_LANGUAGE_OBJ = Language(HTML_LANG_CAPSULE)
            print(f"Wrapped HTML capsule into Language object.")
        except Exception as e:
            print(f"Error wrapping HTML capsule with Language(): {e}")
    if PYTHON_LANG_CAPSULE:
        try:
            PYTHON_LANGUAGE_OBJ = Language(PYTHON_LANG_CAPSULE)
            print(f"Wrapped Python capsule into Language object.")
        except Exception as e:
            print(f"Error wrapping Python capsule with Language(): {e}")
            
    if CPP_LANG_CAPSULE:
        try:
            CPP_LANGUAGE_OBJ = Language(CPP_LANG_CAPSULE)
            print(f"Wrapped C++ capsule into Language object.")
        except Exception as e:
            print(f"Error wrapping C++ capsule with Language(): {e}")

    cs_parser, js_parser, html_parser, py_parser, cpp_parser = None, None, None, None, None

    if CSHARP_LANGUAGE_OBJ:
        cs_parser = Parser()
        cs_parser.language = CSHARP_LANGUAGE_OBJ 
        print("Successfully set C# language to cs_parser.")

    if JAVASCRIPT_LANGUAGE_OBJ:
        js_parser = Parser()
        js_parser.language = JAVASCRIPT_LANGUAGE_OBJ
        print("Successfully set JavaScript language to js_parser.")
        
    if HTML_LANGUAGE_OBJ:
        html_parser = Parser()
        html_parser.language = HTML_LANGUAGE_OBJ
        print("Successfully set HTML language to html_parser.")

    if PYTHON_LANGUAGE_OBJ:
        py_parser = Parser()
        py_parser.language = PYTHON_LANGUAGE_OBJ
        print("Successfully set Python language to py_parser.")

    if CPP_LANGUAGE_OBJ:
        cpp_parser = Parser()
        cpp_parser.language = CPP_LANGUAGE_OBJ
        print("Successfully set C++ language to cpp_parser.")
    else:
        print("C/C++ parser will not be available.")

    project_summary = []

    for root, dirs, files in os.walk(args.scan_directory, topdown=True):
        dirs[:] = [d for d in dirs if d not in excluded_dir_names]

        for file in files:
            file_path = os.path.join(root, file)

            if file.endswith(".cs"):
                process_csharp(file_path, cs_parser, project_summary)
            elif file.endswith(".js"):
                 process_javascript(file_path, js_parser, project_summary)
            elif file.endswith(".cshtml"):
                process_cshtml(file_path, html_parser, js_parser, cs_parser, project_summary)
            elif file.endswith(".py"):
                process_python(file_path, py_parser, project_summary)
            elif file.endswith((".cpp", ".h", ".c", ".hpp")):
                process_cpp(file_path, cpp_parser, project_summary)

    try:
        with open(args.output_file, "w", encoding="utf-8") as f:
            if project_summary and project_summary[0].strip() == "":
                project_summary.pop(0)
            f.write("\n".join(project_summary))
        print(f"\nSummary written to {os.path.abspath(args.output_file)}")
    except Exception as e:
        print(f"\nError writing summary to file '{args.output_file}': {e}")

if __name__ == "__main__":
    ts_version_str = "unknown"
    try:
        from importlib import metadata
        ts_version_str = metadata.version('tree-sitter')
    except ImportError:
        try:
            import pkg_resources
            ts_version_str = pkg_resources.get_distribution('tree-sitter').version
        except Exception:
            print("Warning: Could not determine tree-sitter version automatically.")
            pass

    print(f"Using tree-sitter version: {ts_version_str}")
    main()