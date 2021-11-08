"""
http://xpather.com/
"""
import os
import re

from lxml import etree
from pathlib import Path
import datetime

from lib.opml_processor import OPML, Head, Body, Outline, Generator


class MubuPost:
    DATE_FORMAT = '%Y%m%d'

    def __init__(self, output_html_path, use_mubu_img: bool = False):
        assert output_html_path
        p = Path(output_html_path)
        if not p.exists() or not p.is_file():
            raise RuntimeError('Input file is not exist or not a file, please check it. -22')
        self.use_mubu_img = use_mubu_img
        with open(output_html_path, 'r', encoding='utf-8') as source_file:
            dom_bytes = bytes(source_file.read(), encoding='utf-8')
        self.dom = etree.HTML(dom_bytes)
        created_time = os.stat(output_html_path)[-1]
        if created_time > 0:
            dt = datetime.datetime.fromtimestamp(created_time)
            self.created_time = dt.strftime(self.DATE_FORMAT)
        modified_time = os.stat(output_html_path)[-2]
        if modified_time > 0:
            dt = datetime.datetime.fromtimestamp(modified_time)
            self.modified_time = dt.strftime(self.DATE_FORMAT)

    @staticmethod
    def _get_element_attributes(element):
        # like a dict structure
        return element.attrib

    @staticmethod
    def _get_element_source_line(element):
        return element.sourceline

    @staticmethod
    def _get_element_tag(element):
        return element.tag

    @staticmethod
    def _get_element_text(element):
        return element.text

    def _try_find_created_time_in_title(self, title):
        # maybe get a fixed created time in title text
        r = re.compile(r'(\d{8})')
        found = r.findall(title)
        if found and len(found) == 1:
            return found[0]
        else:
            return self.created_time

    def _is_code_span(self, element):
        attrs = self._get_element_attributes(element)
        if 'class' in attrs and attrs['class'] == 'codespan':
            return True
        return False

    @staticmethod
    def _append_content_with_class(text, class_name):
        if not class_name:
            return text
        if class_name == 'codespan':
            return f'`{text}`'
        elif class_name == 'bold':
            return f'**{text}**'
        elif class_name == 'italic':
            return f'*{text}*'
        elif class_name == 'strikethrough':
            return f'~~{text}~~'
        elif 'italic' in class_name and 'bold' in class_name:
            return f'***{text}***'
        else:
            return text

    def _elements_to_outlines(self, element_children):
        ret = []
        for e in element_children:
            class_name = self._get_element_attributes(e)['class']
            is_normal_node = 'node' in class_name.split(' ')
            assert is_normal_node
            heading_r = re.compile(r'heading(\d)')
            h_n = heading_r.findall(class_name)
            content_editor = e.xpath('div[@class="content mm-editor"]')[0]
            content = ''
            if content_editor is not None and len(content_editor) > 0:
                skip_first_one = True
                iterated_elts = set()
                for sub in content_editor.iter():
                    if skip_first_one:
                        skip_first_one = False
                        continue
                    if sub in iterated_elts:
                        continue
                    iterated_elts.add(sub)
                    class_name = sub.attrib['class'] if 'class' in sub.attrib else None
                    text = sub.text
                    if class_name is not None and class_name == 'content-link':
                        link_text = sub.xpath('*[contains(@class, "content-link-text")]')[0]
                        iterated_elts.add(link_text)
                        # print(f'Link text: {link_text.text}')
                        link_mkd = f'[{link_text.text}]({sub.attrib["href"]})'
                        content += link_mkd
                    elif text is not None:
                        content += self._append_content_with_class(text, class_name)
                    else:
                        raise RuntimeError("text is None, -112")
            outline_attrs = {}
            # mubu image
            if self.use_mubu_img:
                nullable_image_list_arr = e.xpath('ul[@class="image-list"]')
                nullable_image_list = None
                if nullable_image_list_arr and len(nullable_image_list_arr) > 0:
                    nullable_image_list = nullable_image_list_arr[0]
                if nullable_image_list is not None:
                    img_list_arr = nullable_image_list.xpath('li[@class="image-item"]')
                    if img_list_arr and len(img_list_arr) > 0:
                        img_arr = []
                        for img_li in img_list_arr:
                            img_arr.append(img_li.xpath('img[@src]')[0].attrib['src'])
                        outline_attrs['mubu_imgs'] = img_arr
            # parse note div ----- START
            mkd_images = []
            mkd_codes = []
            nullable_note_content = e.xpath('div[@class="note mm-editor"]')
            if len(nullable_note_content) > 0:
                content += '\n'
                img_token_re = re.compile(r'.*\!\[.*\]\(')
                code_token_re = re.compile(r'```(.|\n)+```')
                maybe_img_or_code = nullable_note_content[0].xpath('*')
                if maybe_img_or_code and len(maybe_img_or_code) > 0:
                    index_in_elements = 0
                    while len(maybe_img_or_code) > index_in_elements:
                        element = maybe_img_or_code[index_in_elements]
                        element_tag = self._get_element_tag(element)
                        element_text = self._get_element_text(element)
                        if element_text:
                            if element_text.startswith('\n'):
                                element_text = element_text[1:].strip()
                            elif len(element_text) > 1 and element_text.strip()[1] == '\n':
                                # I cant explain this, but it works, this \n is U+200B, encode error
                                element_text = element_text[2:].strip()
                        if element_tag == 'span':
                            if len(img_token_re.findall(element_text)) > 0:
                                # it's a image
                                img_url = element_text + \
                                          maybe_img_or_code[index_in_elements + 1].attrib['href'].rstrip('\n')
                                mkd_images.append(img_url)
                                index_in_elements += 2
                            elif len(code_token_re.findall(element_text)) > 0:
                                # it's a code
                                mkd_codes.append(element_text)
                                index_in_elements += 1
                            else:
                                raise SyntaxError('Wrong token match, now only support markdown code and image style.')
                        else:
                            raise SyntaxError(f'what kind of tag beside "span" will appear at here? error code=118.'
                                              f'--->tag:{element_tag}, text:{element_text} at line:{self._get_element_source_line(element)}')
                if len(mkd_images) > 0:
                    outline_attrs['mkd_imgs'] = mkd_images
                if len(mkd_codes) > 0:
                    outline_attrs['mkd_codes'] = mkd_codes
            # parse note div ----- END
            if h_n and len(h_n) == 1:
                content = (int(h_n[0]) * '#') + ' ' + content
            o = Outline(content, attrs=outline_attrs)
            sub_children = e.xpath('div[@class="children"]/ul/li')
            if sub_children and len(sub_children) > 0:
                for sub_o in self._elements_to_outlines(sub_children):
                    o.append_child(sub_o)
            ret.append(o)
        return ret

    def parse_to_opml(self):
        # <div class="title"> user input text </div>
        title = self._get_element_text(self.dom.xpath('//div[@class="title"]')[0])
        assert title
        self.created_time = self._try_find_created_time_in_title(title)
        source_content = self._get_element_text(self.dom.xpath('//div[@class="publish"]/a')[0])
        if not source_content or str(source_content).strip() != '幕布文档':
            raise SyntaxError('Not MUBU html， please check it. -32')
        node_list_xp = self.dom.xpath('//body/ul[@class="node-list"]')
        if not node_list_xp or len(node_list_xp) != 1:
            raise SyntaxError('Find node-list error, please check the output html. -35')
        root_element = node_list_xp[0]
        outlines_holder = Outline('Stub')
        for c in self._elements_to_outlines(root_element.xpath('li')):
            outlines_holder.append_child(c)
        head = Head(title, create_date=self.created_time, modified_date=self.modified_time)
        body = Body(outlines_holder.sub_outlines)
        return OPML(head, body)


if __name__ == '__main__':
    # p = MubuPost('<your html exported by MUBU>', use_mubu_img=True)
    # opml = p.parse_to_opml()
    # Generator(opml, 'test_blog').write('.')
    pass
