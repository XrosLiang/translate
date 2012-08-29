#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2012 Michal Čihař
#
# This file is part of the Translate Toolkit.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

"""module for handling Android resource files"""

from lxml import etree

from translate.storage import lisa
from translate.storage import base

EOF = None
WHITESPACE = ' \n\t' # Whitespace that we collapse

class AndroidResourceUnit(base.TranslationUnit):
    """A single term in the Android resource file."""
    rootNode = "string"
    languageNode = "string"

    def __init__(self, source, empty=False, **kwargs):
        self.xmlelement = etree.Element(self.rootNode)
        self.xmlelement.tail = '\n'
        if source is not None:
            self.xmlelement.set('name', source)
        super(AndroidResourceUnit, self).__init__(source)

    def _parse(self):
        self.target = self.gettarget()
        self.source = self.getid()

    def getid(self):
        return self.xmlelement.get("name")

    def getcontext(self):
        return self.xmlelement.get("name")

    def setid(self, newid):
        return self.xmlelement.set("name", newid)

    def unescape(self, text):
        '''
        Remove escaping from Android resource.

        Code stolen from android2po
        <https://github.com/miracle2k/android2po>
        '''
        if text is None:
            return None
        # '<' and '>' as literal characters inside a text need to be
        # escaped; this is because we need to differentiate them to
        # actual tags inside a resource string which we write to the
        # .po file as literal '<', '>' characters. As a result, if the
        # user puts &lt; inside his Android resource file, this is how
        # it will end up in the .po file as well.
        # We only do this for '<' and '<' right now, which is of course
        # a hack. We'd need to process at least &amp; as well, because
        # right now '&lt;' and '&amp;lt;' both generate the same on
        # import. However, if we were to do that, a simple non-HTML
        # text like "FAQ & Help" would end up us "FAQ &amp; Help" in
        # the .po - not particularly nice.
        # TODO: I can see two approaches to solve this: Handle things
        # differently depending on whether there are nested tags. We'd
        # be able to handle both '&amp;lt;' in a HTML string and output
        # a nice & character in a plaintext string.
        # Option 2: It might be possible to note the type of encoding
        # we did in a .po comment. That would even allow us to present
        # a string containing tags encoded using entities (but not actual
        # nested XML tags) using plain < and > characters in the .po
        # file. Instead of a comment, we could change the import code
        # to require a look at the original resource xml file to
        # determine which kind of encoding was done.
        text = text.replace('<', '&lt;')
        text = text.replace('>', "&gt;")

        # We need to collapse multiple whitespace while paying
        # attention to Android's quoting and escaping.
        space_count = 0
        active_quote = False
        active_percent = False
        active_escape = False
        formatted = False
        i = 0
        text = list(text) + [EOF]
        while i < len(text):
            c = text[i]

            # Handle whitespace collapsing
            if c is not EOF and c in WHITESPACE:
                space_count += 1
            elif space_count > 1:
                # Remove duplicate whitespace; Pay attention: We
                # don't do this if we are currently inside a quote,
                # except for one special case: If we have unbalanced
                # quotes, e.g. we reach eof while a quote is still
                # open, we *do* collapse that trailing part; this is
                # how Android does it, for some reason.
                if not active_quote or c is EOF:
                    # Replace by a single space, will get rid of
                    # non-significant newlines/tabs etc.
                    text[i-space_count : i] = ' '
                    i -= space_count - 1
                space_count = 0
            elif space_count == 1:
                # At this point we have a single whitespace character,
                # but it might be a newline or tab. If we write this
                # kind of insignificant whitespace into the .po file,
                # it will be considered significant on import. So,
                # make sure that this kind of whitespace is always a
                # standard space.
                text[i-1] = ' '
                space_count = 0
            else:
                space_count = 0

            # Handle quotes
            if c == '"' and not active_escape:
                active_quote = not active_quote
                del text[i]
                i -= 1

            # If the string is run through a formatter, it will have
            # percentage signs for String.format
            if c == '%' and not active_escape:
                active_percent = not active_percent
            elif not active_escape and active_percent:
                formatted = True
                active_percent = False

            # Handle escapes
            if c == '\\':
                if not active_escape:
                    active_escape = True
                else:
                    # A double-backslash represents a single;
                    # simply deleting the current char will do.
                    del text[i]
                    i -= 1
                    active_escape = False
            else:
                if active_escape:
                    # Handle the limited amount of escape codes
                    # that we support.
                    # TODO: What about \r, or \r\n?
                    if c is EOF:
                        # Basically like any other char, but put
                        # this first so we can use the ``in`` operator
                        # in the clauses below without issue.
                        pass
                    elif c == 'n':
                        text[i-1 : i+1] = '\n' # an actual newline
                        i -= 1
                    elif c == 't':
                        text[i-1 : i+1] = '\t' # an actual tab
                        i -= 1
                    elif c in '"\'@':
                        text[i-1 : i] = '' # remove the backslash
                        i -= 1
                    elif c == 'u':
                        # Unicode sequence. Android is nice enough to deal
                        # with those in a way which let's us just capture
                        # the next 4 characters and raise an error if they
                        # are not valid (rather than having to use a new
                        # state to parse the unicode sequence).
                        # Exception: In case we are at the end of the
                        # string, we support incomplete sequences by
                        # prefixing the missing digits with zeros.
                        # Note: max(len()) is needed in the slice due to
                        # trailing ``None`` element.
                        max_slice = min(i+5, len(text)-1)
                        codepoint_str = "".join(text[i+1 : max_slice])
                        if len(codepoint_str) < 4:
                            codepoint_str = u"0" * (4-len(codepoint_str)) + codepoint_str
                        print repr(codepoint_str)
                        try:
                            # We can't trust int() to raise a ValueError,
                            # it will ignore leading/trailing whitespace.
                            if not codepoint_str.isalnum():
                                raise ValueError(codepoint_str)
                            codepoint = unichr(int(codepoint_str, 16))
                        except ValueError:
                            raise ValueError('bad unicode escape sequence')

                        text[i-1 : max_slice] = codepoint
                        i -= 1
                    else:
                        # All others, remove, like Android does as well.
                        # However, Android does so silently, we show a
                        # warning so the dev can fix the problem.
                        raise ValueError('Resource "%s": removing unsupported '
                                  'escape sequence "%s"' % (
                                    name, "".join(text[i-1 : i+1])))
                        text[i-1 : i+1] = ''
                        i -= 1
                    active_escape = False

            i += 1

        # Join the string together again, but w/o EOF marker
        return "".join(text[:-1])

    def escape(self, text):
        '''
        Escape all the characters which need to be escaped in an Android XML file.
        '''
        if text is None:
            return
        text = text.replace('\\', '\\\\')
        text = text.replace('\n', '\\n')
        text = text.replace('\t', '\\t')
        text = text.replace('\'', '\\\'')
        text = text.replace('"', '\\"')
        if text.startswith('@'):
            text = '\\@' + text[1:]
        return text

    def settarget(self, target):
        target = self.escape(target)
        self.xmlelement.text = target
        super(AndroidResourceUnit, self).settarget(target)

    def gettarget(self, lang=None):
        target = self.xmlelement.text
        return self.unescape(target)

    target = property(gettarget, settarget)

    def getlanguageNode(self, lang=None, index=None):
        return self.xmlelement

    def createfromxmlElement(cls, element):
        term = cls(None, empty=True)
        term.xmlelement = element
        term._parse()
        return term
    createfromxmlElement = classmethod(createfromxmlElement)

    def __str__(self):
        return etree.tostring(self.xmlelement, pretty_print=True,
                              encoding='utf-8')

    def __eq__(self, other):
        return (str(self) == str(other))

class AndroidResourceFile(lisa.LISAfile):
    """Class representing a Android resource file store."""
    UnitClass = AndroidResourceUnit
    Name = _("Android Resource")
    Mimetypes = ["application/xml"]
    Extensions = ["xml"]
    rootNode = "resources"
    bodyNode = "resources"
    XMLskeleton = '''<?xml version="1.0" encoding="utf-8"?>
<resources></resources>'''

    def initbody(self):
        """Initialises self.body so it never needs to be retrieved from the
        XML again."""
        self.namespace = self.document.getroot().nsmap.get(None, None)
        self.body = self.document.getroot()

    def set_base_resource(self, storefile):
        """Loads base resource (containing English strings and all messages)."""
        # Load resource
        r = AndroidResourceFile.parsefile(storefile)
        # We will need index
        self.require_index()
        # Update all units
        for unit in r.units:
            our_unit = self.findid(unit.getid())
            if our_unit is None:
                newunit = AndroidResourceUnit(unit.target)
                newunit.setid(unit.getid())
                newunit.target = ''
                self.addunit(newunit)
            else:
                our_unit.source = unit.target
        self.makeindex()
