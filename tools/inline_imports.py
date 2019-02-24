#!/usr/bin/env python

import argparse
from os import path
import re
from bs4 import BeautifulSoup

ROOT = path.join(path.dirname(path.realpath(__file__)), '..')
JS_DIR = path.join(ROOT, 'src', 'js')


def get_document(content):
    return BeautifulSoup(content, 'html5lib')  # OBE: , from_encoding='utf-8')


def generate_inline_file(source_file_path):
    source_file_path = path.realpath(source_file_path)
    final_doc = get_document('')
    with open(source_file_path) as fh:
        doc = get_document(fh.read())
    already_processed = set()

    # Process each javascript module declared in the original file
    modules = doc.select('script[type="module"]')
    for module in modules:
        module_path = path.join(JS_DIR, module['filename'])
        module.decompose()
        process_js_module(module_path, already_processed, final_doc)

    # Append other head elements from the original file
    for child in doc.head.children:
        if str(child).strip():
            final_doc.head.append(child)

    # Append a script tag containing createCustomElement() to the head
    script_tag = generate_create_custom_element()
    final_doc.head.append(script_tag)

    # Append the stat-block tree to the body
    stat_block_tag = doc.find('stat-block')
    final_doc.body.append(stat_block_tag)

    return final_doc


def process_js_module(module_path, already_processed, final_doc):
    module_path = path.realpath(module_path)
    if module_path in already_processed:
        return None
    already_processed.add(module_path)

    with open(path.realpath(module_path)) as fh:
        content = fh.read()

    # Process any imported modules if they haven't been processed already
    imports = re.findall(r'(?<=import \').*(?=\')', content)
    for import_path in imports:
        import_path = path.join(ROOT, import_path.lstrip('/'))
        process_js_module(import_path, already_processed, final_doc)

    # Find the last fetch() in the module to get the path to the HTML template
    fetches = re.findall(r'(?<=fetch\(\').*(?=\'\))', content)
    template_path = path.join(ROOT, fetches[-1])
    template_name = path.splitext(path.basename(template_path))[0]

    # Convert the module into a pair of inline template and script tags,
    # and add them to the body of the final document
    template_tag = generate_template_tag(template_name, template_path)
    script_tag = generate_script_tag(template_name, content)

    final_doc.body.append(template_tag)
    final_doc.body.append(script_tag)


def generate_create_custom_element():
    doc = get_document('')
    cce_fn = path.realpath(
        path.join(JS_DIR, 'helpers', 'create-custom-element.js')
    )
    with open(cce_fn) as fh:
        content = fh.read()
    content = content.replace('export ', '')

    script_tag = doc.new_tag('script')
    script_tag.string = content

    return script_tag


def generate_template_tag(template_name, template_path):
    with open(path.realpath(template_path)) as fh:
        template_doc = get_document(fh.read())

    template_tag = template_doc.new_tag('template', id=template_name)
    for child in template_doc.head.children:
        template_tag.append(child)
    for child in template_doc.body.children:
        template_tag.append(child)

    return template_tag


def generate_script_tag(template_name, content):
    doc = get_document('')
    script_tag = doc.new_tag('script')

    # Special case: Extract additional javascript functions
    #               for the abilities-block tag only
    if template_name == 'abilities-block':
        javascript_content = extract_inline_js(content)
        script_tag.string = f"""{{
  {javascript_content}
  let templateElement = document.getElementById('{template_name}');
  createCustomElement('{template_name}', templateElement.content, elementClass);
}}"""
    else:
        script_tag.string = f"""{{
  let templateElement = document.getElementById('{template_name}');
  createCustomElement('{template_name}', templateElement.content);
}}"""

    return script_tag


def extract_inline_js(content):
    extracted_content = ''
    in_extraction_mode = False
    for line in content.splitlines():
        if not in_extraction_mode:
            if '// Inline extraction START' in line:
                in_extraction_mode = True
        elif '// Inline extraction END' in line:
            in_extraction_mode = False
        else:
            extracted_content += line + '\n'
    return extracted_content


def main(filename):
    return '\n'.join(
        ('<!DOCTYPE html>', str(generate_inline_file(path.realpath(filename))))
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Inlines HTML imports.')
    parser.add_argument('--filename', '-f', required=True,
                        help='file to inline')
    parser.add_argument('--output', '-o', help='file output', default=None)
    args = parser.parse_args()
    compiled_doc = main(args.filename)
    if args.output is None:
        print(compiled_doc)
    else:
        with open(path.realpath(args.output), 'w') as file:
            file.write(compiled_doc)
