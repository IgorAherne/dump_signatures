# dump_signatures
Creates a txt that represents an overview of your codebase.

Populates this txt with functions taken from your files (names, args).</br>
Txt can then be given to LLMs, for a better context.

Understands:
- C++ and C
- C# files
- Python files
- JavaScript 
- CSHTML
- ignores the rest

## Installation:

1) `git clone https://github.com/IgorAherne/dump_signatures.git`
2) `cd dump_signatures`
3) `python -m venv venv`
4) `.\venv\Scripts\activate`
5) `python -m pip install -r requirements.txt`

## Usage

The script is run from the command line and accepts two optional arguments:

`--scan_directory <path>`: The path to the directory you want to scan. Defaults to the current directory `(.)`
`--output_file <path>`: The name of the file to save the summary to. Defaults to ``./code_summary.txt`

By default it ignores folders `venv, git, obj, bin, .vs, node_modules, tmp, temp`</br>
You can adjust the `excluded_dir_names` inside the `summarize_code.py` to skip additional folders.

---

### Examples

**1. Scan the current directory (and all its subfolders):**
(If you place the script in the root of your project)
```bash
python summarize_code.py
```

**2. Scan the parent directory (and all its subfolders):**
(Useful if you cloned this tool into a subfolder of your project)
```bash
python summarize_code.py --scan_directory ..
```

**3. Scan a specific project folder (and all its subfolders) and define a custom output file:**
```bash
python summarize_code.py --scan_directory "C:\Users\You\Projects\MyWebApp" --output_file "my_webapp_summary.txt"
```

---

### Sample Output

The generated `code_summary.txt` will look something like this:

```
-- FILE: .\..\Assets\_gm\Features\StableDiffusion\Controlnet\ControlNetUnit_UI.cs (C#) --
  USINGS: System, System.Collections, TMPro, UnityEngine, UnityEngine.UI
namespace spz
  class ControlNetUnit_UI
    bool _isForPreviewOnly;
    Toggle _lowVRAM_toggle;
    ControlNetUnit_Dropdowns dropdowns { get; }
    ControlNetUnit_Dropdowns _dropdowns;
    ControlNetUnit_ImagesDisplay _imgsDisplay;
    CircleSlider_Snapping_UI _endingControl_step;
    GameObject _headerMenu_go;
    bool _wasCreatedViaLoad;
    bool isActivated { get; }
    bool hasAtLeastSomeModel { get; }
    void isReferencePreprocessor()
```
