import fitz
import os
import re
from datetime import datetime


def extract_text_with_format(pdf_path):
    doc = fitz.open(pdf_path)
    all_pages = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        page_lines = []
        
        for block in blocks:
            if block["type"] == 0:
                lines = block["lines"]
                for line in lines:
                    spans = line["spans"]
                    line_text = ""
                    line_styles = []
                    
                    for span in spans:
                        text = span["text"]
                        size = span["size"]
                        flags = span["flags"]
                        font = span["font"]
                        
                        is_bold = flags & 2 != 0 or "Bold" in font or "bold" in font.lower()
                        is_italic = flags & 1 != 0
                        
                        style_info = {
                            "text": text,
                            "size": size,
                            "bold": is_bold,
                            "italic": is_italic,
                            "font": font,
                            "bbox": span["bbox"]
                        }
                        line_styles.append(style_info)
                        line_text += text
                    
                    if line_text.strip():
                        page_lines.append({
                            "text": line_text.strip(),
                            "styles": line_styles,
                            "avg_size": sum(s["size"] for s in line_styles) / len(line_styles) if line_styles else 12,
                            "bbox": line["bbox"] if "bbox" in line else (0, 0, 0, 0)
                        })
        
        all_pages.append(page_lines)
    
    doc.close()
    return all_pages


def clean_text(text):
    text = re.sub(r'[·•●○■□▲△▼▽◆◇★☆…]{3,}', ' ', text)
    text = re.sub(r'[\.．]{5,}', ' ', text)
    text = re.sub(r'[_]{5,}', ' ', text)
    text = re.sub(r'…{3,}', ' ', text)
    text = re.sub(r'—{3,}', '— ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_toc_entry(text):
    match = re.match(r'^(.+?)\s*[\.．…·]*\s*(\d+)\s*$', text)
    if match and len(match.group(1)) > 2:
        return match.group(1).strip(), match.group(2).strip()
    return None, None


def merge_broken_lines(lines):
    if len(lines) < 2:
        return lines
    
    merged = []
    i = 0
    
    while i < len(lines):
        current = lines[i]
        current_text = current.get("cleaned_text", current["text"])
        
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            next_text = next_line.get("cleaned_text", next_line["text"])
            
            if re.match(r'^\d+[.、]?$', current_text) and re.match(r'^\d+[\s．]', next_text):
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                merged.append(current)
                i += 2
                continue
            
            if re.match(r'^.*\d+\.$', current_text) and re.match(r'^\d+[\s．].*', next_text):
                if len(current_text) < 15:
                    merged_text = current_text + next_text
                    current["cleaned_text"] = merged_text
                    current["text"] = merged_text
                    merged.append(current)
                    i += 2
                    continue
            
            if current_text.endswith(('—', '-', '～', '~')) and len(current_text) < 15:
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                merged.append(current)
                i += 2
                continue
            
            if re.match(r'^.*\d+\.$', current_text) and re.match(r'^\d+mm', next_text):
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                merged.append(current)
                i += 2
                continue
            
            if re.match(r'^.*\d+\.$', current_text) and re.match(r'^[0-9+\-][\d.]*', next_text) and len(next_text) < 10:
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                merged.append(current)
                i += 2
                continue
            
            if re.match(r'^[（(]\s*\w+\s*[)）]$', current_text):
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                merged.append(current)
                i += 2
                continue
        
        merged.append(current)
        i += 1
    
    result = []
    i = 0
    while i < len(merged):
        current = merged[i]
        current_text = current.get("cleaned_text", current["text"])
        
        if i + 1 < len(merged):
            next_line = merged[i + 1]
            next_text = next_line.get("cleaned_text", next_line["text"])
            
            if re.match(r'^[\d.]+$', current_text) and re.match(r'^\d', next_text) and len(current_text) < 10:
                merged_text = current_text + next_text
                current["cleaned_text"] = merged_text
                current["text"] = merged_text
                result.append(current)
                i += 2
                continue
        
        result.append(current)
        i += 1
    
    return result


def convert_to_markdown(page_contents, pdf_filename):
    md_lines = []
    md_lines.append(f"# {os.path.splitext(pdf_filename)[0]}")
    md_lines.append("")
    
    all_lines = []
    for page_content in page_contents:
        for line in page_content:
            cleaned = clean_text(line["text"])
            if cleaned:
                line["cleaned_text"] = cleaned
                all_lines.append(line)
    
    if not all_lines:
        return "\n".join(md_lines)
    
    all_lines = merge_broken_lines(all_lines)
    
    sizes = [line["avg_size"] for line in all_lines]
    sizes_sorted = sorted(set(sizes), reverse=True)
    
    heading_sizes = []
    if len(sizes_sorted) >= 5:
        heading_sizes = sizes_sorted[:5]
    elif len(sizes_sorted) >= 3:
        heading_sizes = sizes_sorted[:3]
    else:
        heading_sizes = sizes_sorted[:1]
    
    prev_line_text = None
    in_toc = False
    
    for i, line in enumerate(all_lines):
        text = line.get("cleaned_text", line["text"])
        avg_size = line["avg_size"]
        styles = line["styles"]
        
        is_bold_line = all(s["bold"] for s in styles) if styles else False
        
        if text in ["目  次", "目次", "目录", "前  言", "前言", "引  言", "引言"]:
            md_lines.append(f"## {text}")
            md_lines.append("")
            in_toc = text in ["目  次", "目次", "目录"]
            prev_line_text = None
            continue
        
        if re.match(r'^\d+(\.\d+)*\s+\S', text) and len(text) < 120 and is_bold_line:
            heading_num = re.match(r'^\d+(\.\d+)*', text).group()
            level = len(heading_num.split('.'))
            level = min(level + 1, 6)
            md_lines.append(f"{'#' * level} {text}")
            md_lines.append("")
            in_toc = False
            prev_line_text = None
            continue
        
        if re.match(r'^第[一二三四五六七八九十百千]+章', text) and len(text) < 100:
            md_lines.append(f"## {text}")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^[一二三四五六七八九十]+、', text) and len(text) < 100:
            md_lines.append(f"### {text}")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^（[一二三四五六七八九十]+）', text) and len(text) < 100:
            md_lines.append(f"#### {text}")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]', text) and len(text) < 100:
            md_lines.append(f"- {text}")
            prev_line_text = None
            continue
        
        if avg_size in heading_sizes and is_bold_line and len(text) < 150:
            level = heading_sizes.index(avg_size) + 2
            level = min(level, 6)
            md_lines.append(f"{'#' * level} {text}")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if in_toc:
            title, page_num = extract_toc_entry(text)
            if title and page_num and title != page_num:
                md_lines.append(f"- {title} ...... {page_num}")
                prev_line_text = None
                continue
        
        if re.match(r'^表\s*\d+', text) and len(text) < 80:
            md_lines.append(f"> **{text}**")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^图\s*\d+', text) and len(text) < 80:
            md_lines.append(f"> **{text}**")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^[a-zA-Z]+\s*[:：]\s*', text):
            md_lines.append(f"**{text}**")
            md_lines.append("")
            prev_line_text = None
            continue
        
        if re.match(r'^\s*[-*•●○■□▲△▼▽◆◇★☆]\s*', text):
            text = re.sub(r'^\s*[-*•●○■□▲△▼▽◆◇★☆]\s*', '- ', text)
            md_lines.append(text)
            prev_line_text = None
            continue
        
        if re.match(r'^\s*\d+\s*[.、)）]\s*', text):
            md_lines.append(text)
            prev_line_text = None
            continue
        
        if prev_line_text and not re.match(r'^[#\->\s*]', prev_line_text) and not re.match(r'^[#\->\s*]', text):
            if len(prev_line_text) > 0 and not prev_line_text.endswith(('。', '！', '？', '；', '：', '.', '!', '?', ';', ':')):
                md_lines[-1] += text
            else:
                md_lines.append(text)
        else:
            md_lines.append(text)
        
        prev_line_text = text
    
    result = "\n".join(md_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def convert_pdf_to_md(pdf_path, output_dir):
    filename = os.path.basename(pdf_path)
    md_filename = os.path.splitext(filename)[0] + ".md"
    md_path = os.path.join(output_dir, md_filename)
    
    page_contents = extract_text_with_format(pdf_path)
    markdown_content = convert_to_markdown(page_contents, filename)
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    return md_path


def main():
    pdf_dir = r"d:\dl\电力国标PDF"
    md_dir = r"d:\dl\电力国标md"
    progress_file = os.path.join(pdf_dir, "转换进度.md")
    
    if not os.path.exists(md_dir):
        os.makedirs(md_dir)
    
    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    pdf_files.sort()
    
    total = len(pdf_files)
    completed = 0
    failed = 0
    
    print(f"找到 {total} 个PDF文件")
    print("=" * 50)
    
    with open(progress_file, "r", encoding="utf-8") as f:
        progress_content = f.read()
    
    progress_content = re.sub(r'已完成：\d+', '已完成：0', progress_content)
    progress_content = re.sub(r'待处理：\d+', f'待处理：{total}', progress_content)
    progress_content = re.sub(r'\| 已完成 \| [^|]+\|', '| 待处理 | - |', progress_content)
    progress_content = re.sub(r'\| 失败 \| [^|]+\|', '| 待处理 | - |', progress_content)
    
    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(pdf_dir, pdf_file)
        print(f"[{i}/{total}] 正在转换: {pdf_file}")
        
        try:
            md_path = convert_pdf_to_md(pdf_path, md_dir)
            completed += 1
            print(f"  ✓ 成功: {os.path.basename(md_path)}")
            
            old_pattern = r'\| ' + str(i) + r' \| ' + re.escape(pdf_file) + r' \| [^|]+ \| [^|]+ \|'
            new_text = "| " + str(i) + " | " + pdf_file + " | 已完成 | " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " |"
            progress_content = re.sub(old_pattern, new_text, progress_content)
            
            pending = total - completed - failed
            progress_content = re.sub(r'已完成：\d+', f'已完成：{completed}', progress_content)
            progress_content = re.sub(r'待处理：\d+', f'待处理：{pending}', progress_content)
            
            with open(progress_file, "w", encoding="utf-8") as f:
                f.write(progress_content)
                
        except Exception as e:
            failed += 1
            print(f"  ✗ 失败: {str(e)}")
            
            old_pattern = r'\| ' + str(i) + r' \| ' + re.escape(pdf_file) + r' \| [^|]+ \| [^|]+ \|'
            new_text = "| " + str(i) + " | " + pdf_file + " | 失败 | " + str(e)[:30] + " |"
            progress_content = re.sub(old_pattern, new_text, progress_content)
            
            with open(progress_file, "w", encoding="utf-8") as f:
                f.write(progress_content)
    
    print("=" * 50)
    print(f"转换完成！成功: {completed}, 失败: {failed}, 总计: {total}")


if __name__ == "__main__":
    main()
