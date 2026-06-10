from __future__ import annotations

import html
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class TextBox:
    text: str
    left: int
    top: int
    width: int
    height: int
    font_size: int
    color: str
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TextBox":
        return cls(
            text=str(data.get("text", "")),
            left=int(data.get("left", 0)),
            top=int(data.get("top", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            font_size=int(data.get("font_size", 12)),
            color=str(data.get("color", "rgb(0, 0, 0)")),
            confidence=float(data.get("confidence", 0.0)),
        )


def write_layout_json(
    output_path: Path,
    image_path: Path,
    image_width: int,
    image_height: int,
    boxes: Iterable[TextBox],
) -> None:
    payload = {
        "image": str(image_path.as_posix()),
        "width": image_width,
        "height": image_height,
        "boxes": [asdict(box) for box in boxes],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_html(
    output_path: Path,
    background_path: Path,
    image_width: int,
    image_height: int,
    boxes: Iterable[TextBox],
) -> None:
    import urllib.parse
    rel_background = os.path.relpath(background_path, output_path.parent)
    rel_background = rel_background.replace("\\", "/")
    # Percent encode quotes, spaces, etc. for CSS compatibility
    url_background = urllib.parse.quote(rel_background)
    spans = "\n".join(_render_span(box) for box in boxes)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Interactive Slide Editor - Layout Extraction</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: #0ea5e9;
      --primary-hover: #0284c7;
      --bg-dark: #0f172a;
      --bg-card: rgba(30, 41, 59, 0.8);
      --border-color: rgba(255, 255, 255, 0.1);
      font-family: 'Inter', sans-serif;
    }}
    
    * {{
      box-sizing: border-box;
    }}
    
    body {{
      margin: 0;
      background: var(--bg-dark);
      color: #f8fafc;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    /* Header & Navigation Bar */
    header {{
      background: rgba(15, 23, 42, 0.9);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 100;
    }}

    .title-area h1 {{
      margin: 0;
      font-size: 1.1rem;
      font-weight: 600;
      background: linear-gradient(to right, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    
    .title-area p {{
      margin: 2px 0 0 0;
      font-size: 0.75rem;
      color: #94a3b8;
    }}

    /* Floating Interactive Toolbar */
    .editor-toolbar {{
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      padding: 8px 16px;
      border-radius: 12px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
      position: fixed;
      top: 75px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 90;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    
    .editor-toolbar.visible {{
      opacity: 1;
      pointer-events: auto;
      transform: translateX(-50%) translateY(0);
    }}

    .toolbar-group {{
      display: flex;
      align-items: center;
      gap: 4px;
      border-right: 1px solid var(--border-color);
      padding-right: 8px;
    }}
    
    .toolbar-group:last-child {{
      border-right: none;
      padding-right: 0;
    }}

    .toolbar-select {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-color);
      color: #f8fafc;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.85rem;
      outline: none;
      cursor: pointer;
    }}

    .toolbar-btn {{
      background: transparent;
      border: 1px solid transparent;
      color: #cbd5e1;
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s ease;
    }}
    
    .toolbar-btn:hover {{
      background: rgba(255, 255, 255, 0.1);
      color: #fff;
    }}
    
    .toolbar-btn.active {{
      background: var(--primary);
      color: #fff;
    }}
    
    .size-input {{
      width: 45px;
      text-align: center;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-color);
      color: #f8fafc;
      padding: 4px;
      border-radius: 6px;
      font-size: 0.85rem;
    }}
    
    .color-picker-wrapper {{
      position: relative;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      border: 2px solid #fff;
      overflow: hidden;
      cursor: pointer;
    }}
    
    .color-picker-wrapper input[type="color"] {{
      position: absolute;
      top: -10px;
      left: -10px;
      width: 48px;
      height: 48px;
      cursor: pointer;
      border: none;
      background: none;
    }}

    /* Main Workspace area */
    .workspace {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px;
      position: relative;
      overflow: auto;
      background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%);
    }}

    .slide-wrapper {{
      position: relative;
      box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.7);
      transition: transform 0.1s ease-out;
    }}

    .slide {{
      position: relative;
      width: {image_width}px;
      height: {image_height}px;
      background-image: url("{url_background}");
      background-size: {image_width}px {image_height}px;
      background-repeat: no-repeat;
    }}

    .text-layer {{
      position: absolute;
      inset: 0;
    }}

    /* OCR Extracted Text Box style */
    .ocr-text {{
      position: absolute;
      box-sizing: border-box;
      white-space: pre-wrap;
      overflow: visible;
      line-height: 1.2;
      letter-spacing: 0;
      outline: none;
      border: 1px dashed transparent;
      padding: 2px;
      transition: border-color 0.15s ease;
      cursor: text;
    }}
    
    .ocr-text:hover {{
      border-color: rgba(14, 165, 233, 0.4);
    }}
    
    /* Active editing box (like Image 2) */
    .ocr-text.active {{
      border: 2px solid var(--primary);
      z-index: 1000;
      background: rgba(14, 165, 233, 0.05);
    }}

    /* Selection handles */
    .ocr-text.active::before,
    .ocr-text.active::after,
    .ocr-text.active-handle-lt,
    .ocr-text.active-handle-rt {{
      /* We can construct custom dot handles on corners */
    }}
    
    .handle {{
      position: absolute;
      width: 8px;
      height: 8px;
      background: #fff;
      border: 2px solid var(--primary);
      border-radius: 50%;
      pointer-events: none;
      display: none;
      z-index: 1001;
    }}
    
    .ocr-text.active .handle {{
      display: block;
    }}
    
    .handle-tl {{ top: -5px; left: -5px; cursor: nwse-resize; }}
    .handle-tr {{ top: -5px; right: -5px; cursor: nesw-resize; }}
    .handle-bl {{ bottom: -5px; left: -5px; cursor: nesw-resize; }}
    .handle-br {{ bottom: -5px; right: -5px; cursor: nwse-resize; }}
  </style>
</head>
<body>
  <header>
    <div class="title-area">
      <h1>Slide Layout Editor & Visualizer</h1>
      <p>Interactive WYSIWYG overlay for layout verification</p>
    </div>
    <div style="font-size: 0.85rem; color: #64748b;">
      Dimension: {image_width}x{image_height} | Double-click text to edit
    </div>
  </header>

  <!-- Formatting Toolbar (looks like Image 2) -->
  <div class="editor-toolbar" id="toolbar">
    <!-- Font Family -->
    <div class="toolbar-group">
      <select class="toolbar-select" id="fontFamily">
        <option value="Inter">Inter</option>
        <option value="Arial, sans-serif">Arial</option>
        <option value="Georgia, serif">Georgia</option>
        <option value="'Courier New', monospace">Courier</option>
        <option value="'Times New Roman', serif">Times</option>
      </select>
    </div>

    <!-- Font Size Controls -->
    <div class="toolbar-group">
      <button class="toolbar-btn" id="sizeDec">−</button>
      <input type="text" class="size-input" id="fontSizeInput" value="12" />
      <button class="toolbar-btn" id="sizeInc">+</button>
    </div>

    <!-- Styles (Bold, Italic, Underline) -->
    <div class="toolbar-group">
      <button class="toolbar-btn" id="btnBold">B</button>
      <button class="toolbar-btn" id="btnItalic">I</button>
      <button class="toolbar-btn" id="btnUnderline">U</button>
    </div>

    <!-- Alignments -->
    <div class="toolbar-group">
      <button class="toolbar-btn" id="btnAlignLeft">⫷</button>
      <button class="toolbar-btn" id="btnAlignCenter">≡</button>
      <button class="toolbar-btn" id="btnAlignRight">⫸</button>
    </div>

    <!-- Color -->
    <div class="toolbar-group">
      <div class="color-picker-wrapper" id="colorWrapper">
        <input type="color" id="textColorPicker" value="#000000" />
      </div>
    </div>
  </div>

  <main class="workspace">
    <div class="slide-wrapper" id="wrapper">
      <section class="slide" aria-label="OCR extracted slide">
        <div class="text-layer" id="textLayer">
{spans}
        </div>
      </section>
    </div>
  </main>

  <script>
    const imageWidth = {image_width};
    const imageHeight = {image_height};
    
    const wrapper = document.getElementById('wrapper');
    const toolbar = document.getElementById('toolbar');
    
    // Auto-scale slide to fit viewport nicely
    function adjustScale() {{
      const workspace = document.querySelector('.workspace');
      const margin = 80;
      const scaleX = (workspace.clientWidth - margin) / imageWidth;
      const scaleY = (workspace.clientHeight - margin) / imageHeight;
      const scale = Math.min(scaleX, scaleY, 1.0); // Don't upscale past 100%
      
      wrapper.style.transform = `scale(${{scale}})`;
      wrapper.style.width = `${{imageWidth}}px`;
      wrapper.style.height = `${{imageHeight}}px`;
    }}
    
    window.addEventListener('resize', adjustScale);
    adjustScale();
    setTimeout(adjustScale, 100);

    // Interactive Box Selection & Styling
    let activeBox = null;
    
    const textLayer = document.getElementById('textLayer');
    
    // Inject resize handles into all text boxes
    document.querySelectorAll('.ocr-text').forEach(box => {{
      // Add contenteditable
      box.setAttribute('contenteditable', 'true');
      
      // Add handles
      const hTL = document.createElement('div'); hTL.className = 'handle handle-tl';
      const hTR = document.createElement('div'); hTR.className = 'handle handle-tr';
      const hBL = document.createElement('div'); hBL.className = 'handle handle-bl';
      const hBR = document.createElement('div'); hBR.className = 'handle handle-br';
      box.appendChild(hTL);
      box.appendChild(hTR);
      box.appendChild(hBL);
      box.appendChild(hBR);
      
      box.addEventListener('focus', () => {{
        selectBox(box);
      }});
      
      box.addEventListener('blur', (e) => {{
        // Timeout to allow toolbar buttons click
        setTimeout(() => {{
          if (document.activeElement !== box && !toolbar.contains(document.activeElement)) {{
            deselect();
          }}
        }}, 100);
      }});
    }});
    
    function selectBox(box) {{
      if (activeBox) activeBox.classList.remove('active');
      activeBox = box;
      activeBox.classList.add('active');
      
      // Update toolbar UI values
      const computed = window.getComputedStyle(box);
      document.getElementById('fontSizeInput').value = parseInt(computed.fontSize) || 12;
      document.getElementById('fontFamily').value = computed.fontFamily.split(',')[0].replace(/['"]/g, '');
      
      // Update styles active state
      document.getElementById('btnBold').classList.toggle('active', computed.fontWeight === '700' || computed.fontWeight === 'bold');
      document.getElementById('btnItalic').classList.toggle('active', computed.fontStyle === 'italic');
      document.getElementById('btnUnderline').classList.toggle('active', computed.textDecorationLine.includes('underline'));
      
      // Alignments active state
      document.getElementById('btnAlignLeft').classList.toggle('active', computed.textAlign === 'left');
      document.getElementById('btnAlignCenter').classList.toggle('active', computed.textAlign === 'center');
      document.getElementById('btnAlignRight').classList.toggle('active', computed.textAlign === 'right');
      
      // Color picker
      const rgb = computed.color.match(/\\d+/g);
      if (rgb && rgb.length >= 3) {{
        const hex = "#" + rgb.slice(0,3).map(x => parseInt(x).toString(16).padStart(2, '0')).join('');
        document.getElementById('textColorPicker').value = hex;
        document.getElementById('colorWrapper').style.backgroundColor = hex;
      }}
      
      toolbar.classList.add('visible');
    }}
    
    function deselect() {{
      if (activeBox && document.activeElement !== activeBox) {{
        activeBox.classList.remove('active');
        activeBox = null;
        toolbar.classList.remove('visible');
      }}
    }}
    
    // Toolbar Actions
    document.getElementById('sizeInc').addEventListener('click', () => {{
      if (!activeBox) return;
      let size = parseInt(activeBox.style.fontSize) || 12;
      size += 2;
      activeBox.style.fontSize = `${{size}}px`;
      document.getElementById('fontSizeInput').value = size;
      activeBox.focus();
    }});
    
    document.getElementById('sizeDec').addEventListener('click', () => {{
      if (!activeBox) return;
      let size = parseInt(activeBox.style.fontSize) || 12;
      size = Math.max(6, size - 2);
      activeBox.style.fontSize = `${{size}}px`;
      document.getElementById('fontSizeInput').value = size;
      activeBox.focus();
    }});
    
    document.getElementById('fontSizeInput').addEventListener('change', (e) => {{
      if (!activeBox) return;
      const size = parseInt(e.target.value) || 12;
      activeBox.style.fontSize = `${{size}}px`;
      activeBox.focus();
    }});
    
    document.getElementById('fontFamily').addEventListener('change', (e) => {{
      if (!activeBox) return;
      activeBox.style.fontFamily = e.target.value;
      activeBox.focus();
    }});
    
    document.getElementById('btnBold').addEventListener('click', () => {{
      if (!activeBox) return;
      const isBold = activeBox.style.fontWeight === 'bold';
      activeBox.style.fontWeight = isBold ? 'normal' : 'bold';
      document.getElementById('btnBold').classList.toggle('active', !isBold);
      activeBox.focus();
    }});
    
    document.getElementById('btnItalic').addEventListener('click', () => {{
      if (!activeBox) return;
      const isItalic = activeBox.style.fontStyle === 'italic';
      activeBox.style.fontStyle = isItalic ? 'normal' : 'italic';
      document.getElementById('btnItalic').classList.toggle('active', !isItalic);
      activeBox.focus();
    }});
    
    document.getElementById('btnUnderline').addEventListener('click', () => {{
      if (!activeBox) return;
      const isUnder = activeBox.style.textDecoration === 'underline';
      activeBox.style.textDecoration = isUnder ? 'none' : 'underline';
      document.getElementById('btnUnderline').classList.toggle('active', !isUnder);
      activeBox.focus();
    }});
    
    document.getElementById('btnAlignLeft').addEventListener('click', () => {{
      if (!activeBox) return;
      activeBox.style.textAlign = 'left';
      setAlignActive('btnAlignLeft');
      activeBox.focus();
    }});
    
    document.getElementById('btnAlignCenter').addEventListener('click', () => {{
      if (!activeBox) return;
      activeBox.style.textAlign = 'center';
      setAlignActive('btnAlignCenter');
      activeBox.focus();
    }});
    
    document.getElementById('btnAlignRight').addEventListener('click', () => {{
      if (!activeBox) return;
      activeBox.style.textAlign = 'right';
      setAlignActive('btnAlignRight');
      activeBox.focus();
    }});
    
    function setAlignActive(activeId) {{
      ['btnAlignLeft', 'btnAlignRight', 'btnAlignCenter'].forEach(id => {{
        document.getElementById(id).classList.toggle('active', id === activeId);
      }});
    }}
    
    document.getElementById('textColorPicker').addEventListener('input', (e) => {{
      if (!activeBox) return;
      const color = e.target.value;
      activeBox.style.color = color;
      document.getElementById('colorWrapper').style.backgroundColor = color;
    }});
  </script>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")


def _render_span(box: TextBox) -> str:
    text = html.escape(box.text)
    return (
        '      <span class="ocr-text" '
        f'data-confidence="{box.confidence:.3f}" '
        'style="'
        f"left:{box.left}px; top:{box.top}px; width:{box.width}px; "
        f"min-height:{box.height}px; font-size:{box.font_size}px; "
        f"color:{html.escape(box.color)};"
        f'">{text}</span>'
    )
