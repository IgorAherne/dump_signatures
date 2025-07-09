import os
import argparse
from tree_sitter import Language, Parser # Language is still needed for type hints if used, Parser is essential
import platform 
import re 
import sys # For debugging paths
import inspect # For debugging types


# Simplified excluded_dir_names: no longer need to worry about excluding grammar source folders
# as we are not using them directly for building.
excluded_dir_names = ['.git', 'obj', 'bin', 'venv', '.vs', 'node_modules', 'tmp', 'temp', 'tmp_project_files']


# Language Loading
def load_pip_languages():
    """
    Loads tree-sitter languages from installed pip packages.
    Returns PyCapsule objects.
    """
    CSHARP_LANG_CAPSULE = None
    JAVASCRIPT_LANG_CAPSULE = None
    HTML_LANG_CAPSULE = None
    PYTHON_LANG_CAPSULE = None # --- NEW ---

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

    if not any([CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE]):
        print("Error: No tree-sitter language packages could be loaded.")
        print("Please ensure you have installed the necessary packages, e.g.:")
        print("  pip install tree-sitter-c-sharp tree-sitter-javascript tree-sitter-html tree-sitter-python")
        return None

    return CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE


# --- Helper to get text from a node ---
def get_node_text(node, source_bytes, default=""):
    """Safely gets text from a node, returning default if node is None."""
    if not node:
        return default
    return source_bytes[node.start_byte:node.end_byte].decode("utf8", errors="replace")

# --- C# Analysis ---
def analyze_csharp_node(node, source_bytes, summary, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    if node_type == "compilation_unit":
        for child_idx in range(node.child_count):
            analyze_csharp_node(node.child(child_idx), source_bytes, summary, indent_level)

    elif node_type == "using_directive":
        alias_node = node.child_by_field_name("alias") # This node is of type 'alias_equals'
        name_node = node.child_by_field_name("name")  # This node is the namespace/type name
        static_node = node.child_by_field_name("static") # This node is the 'static' keyword if present
        
        using_parts = []

        if static_node: # Check if 'static' keyword exists for "using static"
            using_parts.append("static")

        alias_name_str = ""
        if alias_node: # alias_node is of type 'alias_equals'
            # The 'alias_equals' node has a 'name' field for the alias identifier
            alias_identifier_node = alias_node.child_by_field_name("name") 
            alias_name_str = get_node_text(alias_identifier_node, source_bytes).strip()
            if alias_name_str:
                using_parts.append(f"{alias_name_str} =")

        namespace_str = get_node_text(name_node, source_bytes).strip()
        if namespace_str:
            using_parts.append(namespace_str)
        
        final_using_text = " ".join(filter(None, using_parts))

        if final_using_text: # Parsed successfully or partially
            summary.append(f"{indent}USING: {final_using_text}")
        else:
            # Fallback: get the whole directive text, clean it up.
            raw_directive_text = get_node_text(node, source_bytes)
            cleaned_text = raw_directive_text.strip()
            if cleaned_text.lower().startswith("using "): # Remove "using " prefix
                cleaned_text = cleaned_text[len("using "):].strip()
            if cleaned_text.endswith(";"): # Remove trailing semicolon
                cleaned_text = cleaned_text[:-1].strip()
            
            if cleaned_text:
                summary.append(f"{indent}USING: {cleaned_text}")
            else:
                summary.append(f"{indent}USING: [MalformedOrEmptyDirective]")


    elif node_type == "namespace_declaration":
        name_node = node.child_by_field_name("name")
        namespace_name = get_node_text(name_node, source_bytes, default="[UnknownNamespace]")
        summary.append(f"{indent}NAMESPACE: {namespace_name}")
        body_node = node.child_by_field_name("body")
        if body_node:
            for child_idx in range(body_node.child_count):
                analyze_csharp_node(body_node.child(child_idx), source_bytes, summary, indent_level + 1)

    elif node_type in ["class_declaration", "struct_declaration", "interface_declaration", "enum_declaration", "record_declaration"]:
        name_node = node.child_by_field_name("name")
        type_params_node = node.child_by_field_name("type_parameters")
        name_str = get_node_text(name_node, source_bytes, default="[UnnamedType]")
        if type_params_node:
            name_str += get_node_text(type_params_node, source_bytes)

        summary.append(f"{indent}{node_type.split('_')[0].upper()}: {name_str}")
        body_node = node.child_by_field_name("body")
        if body_node:
            for child_idx in range(body_node.child_count):
                analyze_csharp_node(body_node.child(child_idx), source_bytes, summary, indent_level + 1)

    elif node_type == "method_declaration":
        return_type_node = node.child_by_field_name("type")
        name_identifier_node = node.child_by_field_name("name") # For regular methods, operators
        explicit_specifier_node = node.child_by_field_name("explicit_interface_specifier") # For explicit interface impl.
        params_node = node.child_by_field_name("parameters")

        method_name_text = ""
        if name_identifier_node:
            method_name_text = get_node_text(name_identifier_node, source_bytes)
        elif explicit_specifier_node:
            method_name_text = get_node_text(explicit_specifier_node, source_bytes)
        else:
            # Attempt to find any identifier if specific fields fail (e.g. complex constructs or parse errors)
            # This is a deeper fallback.
            found_identifier = next((c for c in node.children if c.type == 'identifier'), None)
            if found_identifier:
                 method_name_text = get_node_text(found_identifier, source_bytes)
            else:
                 method_name_text = "[UnknownOrComplexMethodName]"

        params_text = get_node_text(params_node, source_bytes, default="()") # Default to empty params "()"
        # Post-process to clean up excessive newlines and fix indentation
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())

        return_type_text = get_node_text(return_type_node, source_bytes).strip()

        if not return_type_text and method_name_text != "[UnknownOrComplexMethodName]":
            # If no return type text could be parsed, but name is somewhat valid, omit return type.
            summary.append(f"{indent}METH: {method_name_text}{params_text}")
        elif not return_type_text and method_name_text == "[UnknownOrComplexMethodName]":
            # If both are problematic
             summary.append(f"{indent}METH: [UnknownSignature]")
        else: # Both return type and name are likely available or have placeholders
            summary.append(f"{indent}METH: {return_type_text} {method_name_text}{params_text}")

    elif node_type == "constructor_declaration":
        name_node = node.child_by_field_name("name") # This is the class name
        params_node = node.child_by_field_name("parameters")
        constructor_name_text = get_node_text(name_node, source_bytes, default="[UnnamedConstructor]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        # Post-process to clean up excessive newlines and fix indentation
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        summary.append(f"{indent}CONSTRUCTOR: {constructor_name_text}{params_text}")

    elif node_type == "destructor_declaration":
        name_node = node.child_by_field_name("name") # Identifier for the class name
        params_node = node.child_by_field_name("parameters")
        class_name_for_destructor = get_node_text(name_node, source_bytes, default="[UnnamedClass]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        summary.append(f"{indent}DESTRUCTOR: ~{class_name_for_destructor}{params_text}")


    elif node_type == "field_declaration":
        type_node = node.child_by_field_name("type")
        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>")
        var_declaration_node = node.child_by_field_name("declaration")
        if var_declaration_node and var_declaration_node.type == "variable_declaration":
            for i in range(var_declaration_node.child_count):
                child_node = var_declaration_node.child(i)
                if child_node.type == "variable_declarator":
                    name_node_for_field = child_node.child_by_field_name("name")
                    name_text = get_node_text(name_node_for_field, source_bytes, default="[UnnamedField]")
                    summary.append(f"{indent}FIELD: {type_text} {name_text}")
        else: 
            summary.append(f"{indent}FIELD: {type_text} [FieldWithComplexDeclaration]")


    elif node_type == "property_declaration":
        type_node = node.child_by_field_name("type")
        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>")
        
        name_identifier_node = node.child_by_field_name("name")
        explicit_specifier_node = node.child_by_field_name("explicit_interface_specifier")

        name_text = ""
        if name_identifier_node:
            name_text = get_node_text(name_identifier_node, source_bytes)
        elif explicit_specifier_node:
            name_text = get_node_text(explicit_specifier_node, source_bytes)
        
        if name_text:
            summary.append(f"{indent}PROP: {type_text} {name_text}")
        else:
            summary.append(f"{indent}PROP: {type_text} [UnnamedOrComplexProperty]")

    elif node_type == "event_field_declaration": 
        type_node = node.child_by_field_name("type")
        type_text = get_node_text(type_node, source_bytes, default="<unknown_type>")
        var_declaration_node = node.child_by_field_name("declaration")
        if var_declaration_node and var_declaration_node.type == "variable_declaration":
            for i in range(var_declaration_node.child_count):
                child_node = var_declaration_node.child(i)
                if child_node.type == "variable_declarator":
                    name_node_for_event = child_node.child_by_field_name("name")
                    name_text = get_node_text(name_node_for_event, source_bytes, default="[UnnamedEvent]")
                    summary.append(f"{indent}EVENT: {type_text} {name_text}")
        else:
            summary.append(f"{indent}EVENT: {type_text} [EventWithComplexDeclaration]")


    elif node_type == "delegate_declaration":
        return_type_node = node.child_by_field_name("return_type")
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        
        return_type_text = get_node_text(return_type_node, source_bytes, default="<void_or_unknown_type>")
        delegate_name = get_node_text(name_node, source_bytes, default="[UnnamedDelegate]")
        params_text = get_node_text(params_node, source_bytes, default="()")
        summary.append(f"{indent}DELEGATE: {return_type_text} {delegate_name}{params_text}")


def process_csharp(file_path, parser, summary):
    summary.append(f"\n--- FILE: {file_path} (C#) ---")
    if not parser:
        summary.append("  C# parser not available. Skipping.")
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_csharp_node(tree.root_node, source_bytes, summary)
    except Exception as e:
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
        # Post-process to clean up excessive newlines and fix indentation
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
        # Post-process to clean up excessive newlines and fix indentation
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
    summary.append(f"\n-- FILE: {file_path} (JavaScript) --")
    if not parser:
        summary.append("  JavaScript parser not available. Skipping.")
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_javascript_node(tree.root_node, source_bytes, summary)
    except Exception as e:
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
                        analyze_csharp_node(cs_tree.root_node, csharp_code_bytes, summary, indent_level + 1)
                    except Exception as e:
                        summary.append(f"{indent}    Error parsing C# in CSHTML block: {e}")
            elif not cs_parser and match: 
                 summary.append(f"{indent}  C# parser not available for CSHTML block.")
    for child_idx in range(node.child_count):
        analyze_cshtml_node(node.child(child_idx), source_bytes, summary, js_parser, cs_parser, indent_level)


def process_cshtml(file_path, html_parser, js_parser, cs_parser, summary):
    summary.append(f"\n--- FILE: {file_path} (CSHTML) ---")
    if not html_parser:
        summary.append("  HTML parser not available. Skipping CSHTML file.")
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
                summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@model"):
                summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@using"): 
                summary.append(f"  DIRECTIVE: {stripped_line}")
            elif stripped_line.startswith("@inject"):
                summary.append(f"  DIRECTIVE: {stripped_line}")

        tree = html_parser.parse(source_bytes)
        analyze_cshtml_node(tree.root_node, source_bytes, summary, js_parser, cs_parser)
    except Exception as e:
        summary.append(f"  Error processing {file_path}: {e}")


def analyze_python_node(node, source_bytes, summary, indent_level=0):
    indent = "  " * indent_level
    node_type = node.type

    # Recurse through the top-level module
    if node_type == "module":
        for child in node.children:
            analyze_python_node(child, source_bytes, summary, indent_level)
    
    # Handle imports: `from module import something`
    elif node_type == "import_from_statement":
        module_name_node = node.child_by_field_name("module_name")
        module_name = get_node_text(module_name_node, source_bytes)
        
        # This part handles `from module import a, b, c` or `from module import *`
        imported_names_node = node.child_by_field_name("name")
        imported_names = get_node_text(imported_names_node, source_bytes)
        
        summary.append(f"{indent}IMPORT: from {module_name} import {imported_names}")

    # Handle imports: `import module`
    elif node_type == "import_statement":
        name_node = node.child_by_field_name("name")
        module_name = get_node_text(name_node, source_bytes)
        summary.append(f"{indent}IMPORT: {module_name}")

    # Handle decorated definitions (e.g., @app.route)
    elif node_type == "decorated_definition":
        for child in node.children:
            if child.type == "decorator":
                summary.append(f"{indent}DECORATOR: @{get_node_text(child.child_by_field_name('name'), source_bytes)}")
        # The actual function/class is the last child
        definition_node = node.children[-1]
        analyze_python_node(definition_node, source_bytes, summary, indent_level)

    # Handle functions: `def my_func(a, b):`
    elif node_type == "function_definition":
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        func_name = get_node_text(name_node, source_bytes, "[lambda]")
        params_text = get_node_text(params_node, source_bytes, "()")
        # Post-process to clean up excessive newlines and fix indentation
        if '\n' in params_text:
            next_line_indent = indent + "  "
            params_text = re.sub(r'\s*[\r\n]+\s*', '\n' + next_line_indent, params_text.strip())
        summary.append(f"{indent}FUNC: {func_name}{params_text}")
        
        # Optionally, recurse into the function body for nested functions/classes
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                analyze_python_node(child, source_bytes, summary, indent_level + 1)
    
    # Handle classes: `class MyClass(BaseClass):`
    elif node_type == "class_definition":
        name_node = node.child_by_field_name("name")
        class_name = get_node_text(name_node, source_bytes)
        
        superclasses_node = node.child_by_field_name("superclasses")
        superclasses_text = get_node_text(superclasses_node, source_bytes, "")
        
        summary.append(f"{indent}CLASS: {class_name}{superclasses_text}")
        
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                analyze_python_node(child, source_bytes, summary, indent_level + 1)


def process_python(file_path, parser, summary):
    """Wrapper function to process a single Python file."""
    summary.append(f"\n--- FILE: {file_path} (Python) ---")
    if not parser:
        summary.append("  Python parser not available. Skipping.")
        return
    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        tree = parser.parse(source_bytes)
        analyze_python_node(tree.root_node, source_bytes, summary)
    except Exception as e:
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

    CSHARP_LANG_CAPSULE, JAVASCRIPT_LANG_CAPSULE, HTML_LANG_CAPSULE, PYTHON_LANG_CAPSULE = loaded_capsules

    # These will now be actual tree_sitter.Language objects
    CSHARP_LANGUAGE_OBJ = None # Renamed to avoid confusion with the Language class itself
    JAVASCRIPT_LANGUAGE_OBJ = None
    HTML_LANGUAGE_OBJ = None

    if CSHARP_LANG_CAPSULE:
        try:
            CSHARP_LANGUAGE_OBJ = Language(CSHARP_LANG_CAPSULE) # Explicitly wrap the capsule
            print(f"Wrapped C# capsule into Language object. Type: {type(CSHARP_LANGUAGE_OBJ)}, Module: {inspect.getmodule(CSHARP_LANGUAGE_OBJ)}")
        except Exception as e:
            print(f"Error wrapping C# capsule with Language(): {e}")
    if JAVASCRIPT_LANG_CAPSULE:
        try:
            JAVASCRIPT_LANGUAGE_OBJ = Language(JAVASCRIPT_LANG_CAPSULE) # Explicitly wrap
            print(f"Wrapped JavaScript capsule into Language object. Type: {type(JAVASCRIPT_LANGUAGE_OBJ)}, Module: {inspect.getmodule(JAVASCRIPT_LANGUAGE_OBJ)}")
        except Exception as e:
            print(f"Error wrapping JavaScript capsule with Language(): {e}")
    if HTML_LANG_CAPSULE:
        try:
            HTML_LANGUAGE_OBJ = Language(HTML_LANG_CAPSULE) # Explicitly wrap
            print(f"Wrapped HTML capsule into Language object. Type: {type(HTML_LANGUAGE_OBJ)}, Module: {inspect.getmodule(HTML_LANGUAGE_OBJ)}")
        except Exception as e:
            print(f"Error wrapping HTML capsule with Language(): {e}")
    if PYTHON_LANG_CAPSULE:
        try:
            PYTHON_LANGUAGE_OBJ = Language(PYTHON_LANG_CAPSULE)
            print(f"Wrapped Python capsule into Language object. Type: {type(PYTHON_LANGUAGE_OBJ)}, Module: {inspect.getmodule(PYTHON_LANGUAGE_OBJ)}")
        except Exception as e:
            print(f"Error wrapping Python capsule with Language(): {e}")


    cs_parser = None
    if CSHARP_LANGUAGE_OBJ: # Check the wrapped Language object
        cs_parser = Parser()
        print(f"Created cs_parser. Type: {type(cs_parser)}, Module: {inspect.getmodule(cs_parser)}")
        print(f"Attempting to set CSHARP_LANGUAGE_OBJ (type: {type(CSHARP_LANGUAGE_OBJ)}) to cs_parser.language.")
        try:
            cs_parser.language = CSHARP_LANGUAGE_OBJ 
            print("Successfully set C# language to cs_parser.")
        except TypeError as te:
            print(f"TypeError during 'cs_parser.language = CSHARP_LANGUAGE_OBJ': {te}") 
            print(f"Is CSHARP_LANGUAGE_OBJ an instance of tree_sitter.Language? {isinstance(CSHARP_LANGUAGE_OBJ, Language)}")
            print(f"Type of tree_sitter.Language that cs_parser expects: {Language}")
            raise 
    else:
        print("C# parser will not be available (either capsule failed to load or wrapping failed).")

    js_parser = None
    if JAVASCRIPT_LANGUAGE_OBJ: # Check the wrapped Language object
        js_parser = Parser()
        print(f"Created js_parser. Type: {type(js_parser)}, Module: {inspect.getmodule(js_parser)}")
        print(f"Attempting to set JAVASCRIPT_LANGUAGE_OBJ (type: {type(JAVASCRIPT_LANGUAGE_OBJ)}) to js_parser.language.")
        try:
            js_parser.language = JAVASCRIPT_LANGUAGE_OBJ
            print("Successfully set JavaScript language to js_parser.")
        except TypeError as te:
            print(f"TypeError during 'js_parser.language = JAVASCRIPT_LANGUAGE_OBJ': {te}")
            print(f"Is JAVASCRIPT_LANGUAGE_OBJ an instance of tree_sitter.Language? {isinstance(JAVASCRIPT_LANGUAGE_OBJ, Language)}")
            print(f"Type of tree_sitter.Language that js_parser expects: {Language}")
            raise
    else:
        print("JavaScript parser will not be available (either capsule failed to load or wrapping failed).")

    html_parser = None
    if HTML_LANGUAGE_OBJ: # Check the wrapped Language object
        html_parser = Parser()
        print(f"Created html_parser. Type: {type(html_parser)}, Module: {inspect.getmodule(html_parser)}")
        print(f"Attempting to set HTML_LANGUAGE_OBJ (type: {type(HTML_LANGUAGE_OBJ)}) to html_parser.language.")
        try:
            html_parser.language = HTML_LANGUAGE_OBJ
            print("Successfully set HTML language to html_parser.")
        except TypeError as te:
            print(f"TypeError during 'html_parser.language = HTML_LANGUAGE_OBJ': {te}")
            print(f"Is HTML_LANGUAGE_OBJ an instance of tree_sitter.Language? {isinstance(HTML_LANGUAGE_OBJ, Language)}")
            print(f"Type of tree_sitter.Language that html_parser expects: {Language}")
            raise
    else:
        print("HTML parser will not be available (either capsule failed to load or wrapping failed).")

    py_parser = None
    if PYTHON_LANGUAGE_OBJ: # Check the wrapped Language object
        py_parser = Parser()
        print(f"Created py_parser. Type: {type(py_parser)}, Module: {inspect.getmodule(py_parser)}")
        print(f"Attempting to set PYTHON_LANGUAGE_OBJ (type: {type(PYTHON_LANGUAGE_OBJ)}) to py_parser.language.")
        try:
            py_parser.language = PYTHON_LANGUAGE_OBJ
            print("Successfully set Python language to py_parser.")
        except TypeError as te:
            print(f"TypeError during 'py_parser.language = PYTHON_LANGUAGE_OBJ': {te}")
            print(f"Is PYTHON_LANGUAGE_OBJ an instance of tree_sitter.Language? {isinstance(PYTHON_LANGUAGE_OBJ, Language)}")
            print(f"Type of tree_sitter.Language that py_parser expects: {Language}")
            raise
    else:
        print("Python parser will not be available (either capsule failed to load or wrapping failed).")

    project_summary = []

    for root, dirs, files in os.walk(args.scan_directory, topdown=True):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dir_names]

        for file in files:
            file_path = os.path.join(root, file)
            # No need to check if file is in grammar_dir, as we're not building from source

            if file.endswith(".cs"):
                process_csharp(file_path, cs_parser, project_summary)
            elif file.endswith(".js"):
                 process_javascript(file_path, js_parser, project_summary)
            elif file.endswith(".cshtml"):
                process_cshtml(file_path, html_parser, js_parser, cs_parser, project_summary)
            elif file.endswith(".py"):
                process_python(file_path, py_parser, project_summary)

    try:
        with open(args.output_file, "w", encoding="utf-8") as f:
            for line in project_summary:
                f.write(line + "\n")
        print(f"Summary written to {os.path.abspath(args.output_file)}")
    except Exception as e:
        print(f"Error writing summary to file '{args.output_file}': {e}")




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