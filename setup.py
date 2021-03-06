#
# Project Burnet
#
# Copyright IBM, Corp. 2013
#
# Authors:
#  Anthony Liguori <aliguori@us.ibm.com>
#  Adam Litke <agl@linux.vnet.ibm.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#

from distutils.command.build import build
from distutils.cmd import Command
from distutils.core import setup
from glob import glob, iglob
import polib
import os
import subprocess
import time


PROJECT = 'burnet'
VERSION = '0.1'


def make_mo():
    print "compile mo files"
    for path in iglob("i18n/po/*"):
        pofile = os.path.join(path, 'LC_MESSAGES', PROJECT + '.po')
        lang = path.rsplit('/', 1)[1]
        mopath = os.path.join("i18n/mo", lang, 'LC_MESSAGES')
        mofile = os.path.join(mopath, PROJECT + '.mo')
        if (os.path.isfile(pofile) and
            (not os.path.isfile(mofile) or
             os.path.getmtime(mofile) < os.path.getmtime(pofile))):
            po = polib.pofile(pofile)
            if not os.path.isdir(mopath):
                os.makedirs(mopath)
            po.save_as_mofile(mofile)
            print "compile: %s" % mofile


def make_ui():
    def merge_files(src_glob, dst_file):
        with open(dst_file, "w") as outf:
            for path in sorted(glob(src_glob)):
                with open(path) as inf:
                    outf.write(inf.read() + "\n")

    print "Installing unified js and css files"
    merge_files("ui/js/src/*.js", "ui/js/burnet.min.js")

    for path in next(os.walk('ui/css'))[1]:
        if not path.startswith('theme-'):
            continue
        theme = path.split('/')[-1]
        merge_files("ui/css/%s/*.css" % theme, "ui/css/%s.min.css" % theme)


class cmd_make_mo(Command):
    description = "compile po files to mo files"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        make_mo()


class cmd_make_po(Command):
    description = "merge po or create new po files"
    user_options = [
        ('langs=', None,
         "language list to support new po files, delimited by comma"), ]
    file_list = ['ui/pages/*.tmpl']
    pygettext_dir = ['/usr/bin/pygettext',
                     '/usr/bin/pygettext.py',
                     '/usr/share/doc/packages/python/Tools/i18n/pygettext.py']

    def initialize_options(self):
        self.langs = ''

    def finalize_options(self):
        self.langs = self.langs.split(",") if self.langs else []

    def find_pygettext(self):
        for f in self.pygettext_dir:
            if os.access(f, os.F_OK):
                return f
        raise Exception("Unable to find pygettext, please install it")

    def make_pot(self):
        files = " ".join(self.file_list)
        command = 'python %s -v %s' % (self.find_pygettext(), files)
        print command
        retcode = subprocess.call(command, shell=True)
        if retcode == 0:
            print "generate messages.pot successfully"
            return True
        print "generate messages.pot failed"
        return False

    def make_po(self):
        potfile = "messages.pot"
        if not self.make_pot():
            return

        support_langs = [path.rsplit('/', 1)[1]
                         for path in iglob("./i18n/po/*")]
        new_langs = [lang for lang in self.langs if lang not in support_langs]

        for lang in new_langs:
            popath = "./i18n/po/%s/LC_MESSAGES/" % lang
            os.makedirs(popath)

        pot = polib.pofile(potfile)
        pot.metadata["Content-Type"] = 'text/plain; charset=UTF-8'
        pot.metadata["Content-Transfer-Encoding"] = '8bit'
        pot.metadata["Project-Id-Version"] = '%s %s' % (PROJECT,
                                                        VERSION)

        for path in iglob("i18n/po/*/LC_MESSAGES/"):
            pofile = os.path.join(path,  PROJECT + '.po')
            lang = pofile.split("/")[2]
            pot.metadata["Language"] = lang
            podata = time.strftime('%Y-%m-%d %H:%M+0000', time.gmtime())
            if not os.path.isfile(pofile):
                print "Create new po file:\t %s" % pofile
                pot.metadata['PO-Revision-Date'] = podata
                percent = pot.percent_translated()
                pot.save(pofile)
            else:
                print "Update exist po file:\t %s" % pofile
                po = polib.pofile(pofile)
                po.merge(pot)
                po.metadata['PO-Revision-Date'] = podata
                po.metadata["Project-Id-Version"] = '%s %s' % (PROJECT,
                                                               VERSION)
                percent = po.percent_translated()
                po.save()

            print "Percentage of translated messages is: %s%%" % percent

    def run(self):
        self.make_po()


class cmd_info_po(Command):
    description = "get the infomation of po files"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def info_po(self):
        print "get the summary of po files"
        for pofile in iglob("i18n/po/*/LC_MESSAGES/*.po"):
            po = polib.pofile(pofile)
            total = len(po.fuzzy_entries() + po.untranslated_entries() +
                        po.translated_entries() + po.obsolete_entries())
            print "%s:" % pofile
            print "  total:%s\t" % total,
            print "untranslated: %s\t" % len(po.untranslated_entries()),
            print "fuzzy: %s\t" % len(po.fuzzy_entries()),
            print "obsolete: %s\t" % len(po.obsolete_entries())

    def run(self):
        self.info_po()


class cmd_make_ui(Command):
    description = "Build the UI"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        make_ui()


class burnet_build(build):
    def run(self):
        make_mo()
        make_ui()
        build.run(self)

i18n_languages = [v.split('/')[2]
                  for v in glob("i18n/po/*/LC_MESSAGES/%s.po" % PROJECT)]

i18n_files = [("share/burnet/i18n/mo/%s/LC_MESSAGES/%s.mo" % (v, PROJECT),
               ["i18n/mo/%s/LC_MESSAGES/%s.mo" % (v, PROJECT)])
              for v in i18n_languages]

extra_css_files = ["ui/css/theme-default.min.css"]
extra_js_files = ["ui/js/burnet.min.js"]


def all_files(path):
    return ["%s/%s" % (path, f) for f in next(os.walk(path))[2]]

setup(name='burnet',
      version=VERSION,
      package_dir={'': 'src'},
      packages=['burnet'],
      scripts=['bin/burnetd'],
      cmdclass={'make_mo': cmd_make_mo,
                'make_po': cmd_make_po,
                'info_po': cmd_info_po,
                'make_ui': cmd_make_ui,
                'build': burnet_build},
      data_files=[('share/burnet/ui/css',
                        glob('ui/css/*.css') + extra_css_files),
                  ('share/burnet/ui/css/fonts', all_files('ui/css/fonts')),
                  ('share/burnet/ui/css/fonts/novnc',
                        all_files('ui/css/fonts/novnc')),
                  ('share/burnet/ui/css/novnc', all_files('ui/css/novnc')),
                  ('share/burnet/ui/images/theme-default',
                        all_files('ui/images/theme-default')),
                  ('share/burnet/ui/images', all_files('ui/images')),
                  ('share/burnet/ui/js', glob('ui/js/*.js') + extra_js_files),
                  ('share/burnet/ui/js/novnc', glob('ui/js/novnc/*.js')),
                  ('share/burnet/ui/js/novnc/web-socket-js',
                        all_files('ui/js/novnc/web-socket-js')),
                  ('share/burnet/ui/libs', glob('ui/libs/*.js')),
                  ('share/burnet/ui/pages', glob('ui/pages/*.tmpl')),
                  ('share/burnet/ui', glob('ui/*.html')),
                  ('share/burnet/data', []),
                  ('share/burnet/data/screenshots', [])] + i18n_files)
