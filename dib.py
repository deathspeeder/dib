import os
import sys
import re
import io
import shutil
import argparse
import subprocess
from subprocess import CalledProcessError
from jinja2 import Environment, FileSystemLoader

class Image():
    name_string = "[A-Za-z0-9/:._-]+"
    name_pattern = re.compile("^%s$" % name_string)
    parents_string = "%s(,%s)*" % (name_string, name_string)
    parents_pattern = re.compile("^%s$" % parents_string)
    type_pattern = re.compile("^class|trait$")
    version_string = "[A-Za-z0-9_.-]+"
    versions_string = "%s(,%s)*" % (version_string, version_string)
    versions_pattern = re.compile("^%s$" % versions_string)
    index_string = "\[[0-9]+\]"
    index_pattern = re.compile("^%s$" % index_string)
    version_or_index_string = "(%s)|(%s)" % (version_string, index_string)
    name_or_index_string = "(%s)|(%s)" % (name_string, index_string)
    mapping_string = "(%s):(%s):%s" % (version_or_index_string, name_or_index_string, version_string)
    mappings_string = "%s(,%s)*" % (mapping_string, mapping_string)
    mappings_pattern = re.compile("^%s$" % mappings_string)
    def __init__(self, definition, template=None, files=[]):
        self.name = None
        self.type = None
        self.parents = []
        self.parent_images = []
        self.versions = []
        self.mappings = {}
        self.template = template
        self.files = files

        mappings_value = None
        for line in definition.splitlines():
            tokens = line.split('=')
            if len(tokens) > 1:
                key = tokens[0].strip()
                value = tokens[1].strip()
                # print "key=%s value=%s" % (key, value)
                if key == "name" and Image.name_pattern.match(value):
                    self.name = value
                elif key == "type" and Image.type_pattern.match(value):
                    self.type = value
                elif key == "parents" and Image.parents_pattern.match(value):
                    self.parents = value.split(',')
                    self.parent_images = map(lambda x: None, self.parents)
                elif key == "versions" and Image.versions_pattern.match(value):
                    self.versions = value.split(',')
                elif key == "mappings" and Image.mappings_pattern.match(value):
                    mappings_value = value

        # print "self.name %s" % self.name
        # print "self.type %s" % self.type
        # print "self.parent %s" % self.parent
        # print "self.versions %s" % self.versions
        # print "self.mappings %s" % self.mappings
        if self.name == None:
            raise RuntimeError("definition 'name' not found")
        if self.type == None:
            raise RuntimeError("definition 'type' not found")
        if len(self.versions) == 0:
            raise RuntimeError("definition 'versions' not found")
        if self.type == "class" and self.template == None:
            raise RuntimeError("dockerfile template not found")

        if mappings_value != None:
            tokens = mappings_value.split(',')
            for token in tokens:
                parts = token.split(':')
                try:
                    # regex ensured len(parts) > 2
                    version = self.member_of(parts[0], self.versions)
                    parent = self.member_of(parts[1], self.parents)
                    self.mappings[version] = (parent, parts[2])
                except Exception as e:
                #except:
                    #e = sys.exc_info()[0]
                    print "WARN Ignored %s's mapping %s due to %s" % (self.name, mappings_value, e)
    def member_of(self, member, list):
        '''
        May raise ValueError, IndexError
        '''
        if Image.index_pattern.match(member):
            index = int(member[1:-1])
            return list[index]
        else:
            if len(filter(lambda x: x==member, list)) > 0:
                return member
            else:
                raise ValueError("%s not found" % member)

    def __str__(self):
        parent = "[%s]" % ','.join(map(lambda i: "Image(%s)" % i[0].name if i[0]!=None else i[1], zip(self.parent_images, self.parents)))
        return "Image(%s, %s, %s, %s, %s)" % (self.name, self.type, parent, self.versions, self.mappings)

    def __repr__(self):
        return self.__str__()

class LocalDocker:
    header_pattern = re.compile("^REPOSITORY\s+TAG\s+IMAGE ID\s+CREATED\s+SIZE$")
    def __init__(self):
        self.images = []

    def image_of(self, name, version):
        return type('',(object,),{'name':name,'version':version})()

    def cache_images(self):
        try:
            output_images = subprocess.check_output(['docker', 'images'])
        except CalledProcessError as e:
            raise RuntimeError(e)
        lines = output_images.split('\n')
        if len(lines) == 0:
            raise RuntimeError("No output when cache images %s" % output_images)
        if not LocalDocker.header_pattern.match(lines[0]):
            raise RuntimeError("Bad output when cache images %s " % output_images)

        for line in lines[1:]:
            tokens = re.compile("\s+").split(line)
            if len(tokens) > 2:
                image = self.image_of(tokens[0], tokens[1])
                self.images.append(image)

    def build_image(self, name, version, path):
        try:
            output_build = subprocess.check_output([
                'docker', 'build',
                '-t', name + ':' + version,
                path])
        except CalledProcessError as e:
            raise RuntimeError(e)
        #print output_build
        image = self.image_of(name, version)
        self.images.append(image)

    def push_image(self, name, version):
        try:
            output_push = subprocess.check_output([
                'docker', 'push', name + ':' + version])
        except CalledProcessError as e:
            raise RuntimeError(e)

    def cached_image(self, name, version):
        for i in self.images:
            if i.name == name and i.version == version:
                return True
        return False

class Project:
    env = Environment(loader=FileSystemLoader('images'))
    build_dir = "./build"
    image_dir = "./images"

    def __init__(self):
        self.classes = []
        self.docker = LocalDocker()

    def create_image(self, package_file_path, dockerfile_path=None, files=[]):
        package_template = Project.env.get_template(package_file_path)
        package_definition = package_template.render()
        if dockerfile_path == None:
            dockerfile_template = None
        else:
            dockerfile_template = Project.env.get_template(dockerfile_path)
        return Image(package_definition, dockerfile_template, files)

    def load_macros(self):
        temp_file_path = Project.image_dir + "/temp.j2"
        with io.open(temp_file_path, "w", encoding='utf8') as tempfile:
            content = u"""
{% import 'macros.j2' as g -%}
prefix={{g.prefix}}
suffix={{g.suffix}}
"""
            tempfile.write(content)
        temp_template = Project.env.get_template("temp.j2")
        rendered = temp_template.render()
        for line in rendered.splitlines():
            tokens = line.split('=')
            if len(tokens) > 1:
                key = tokens[0].strip()
                value = tokens[1].strip()
                if key == "prefix":
                    self.prefix = value
                    #print "prefix: %s" % value
                if key == "suffix":
                    self.suffix = value
                    #print "suffix: %s" % value
        os.remove(temp_file_path)

    def load_image_definition(self):
        default_dockerfile = 'Dockerfile.j2'
        default_package_file = 'package.j2'
        walk_dir = os.path.abspath(Project.image_dir)
        print "Will walk directory %s for image definitions" % walk_dir

        for root, subdirs, files in os.walk(walk_dir):
            relative_path = os.path.relpath(root, walk_dir)
            package_file_path = os.path.join(relative_path, default_package_file)
            dockerfile_path = os.path.join(relative_path, default_dockerfile)

            # print "root %s" % root
            # print "package %s" % package_file_path
            if os.path.isfile(os.path.join(root, default_package_file)):
                files.remove(default_package_file)
                try:
                    if os.path.isfile(os.path.join(root, default_dockerfile)):
                        files.remove(default_dockerfile)
                    else:
                        dockerfile_path = None
                    abs_files = [os.path.join(root, f) for f in files]
                    image = self.create_image(package_file_path, dockerfile_path, abs_files)
                    if len(filter(lambda c: c.name == image.name, self.classes)) > 0:
                        raise RuntimeError("duplicated image name")
                    self.classes.append(image)
                except RuntimeError as e:
                    print "WARN Ignored path %s due to Error %s" % (package_file_path, e)

        for i in self.classes:
            i.parent_images = []
            for n in i.parents:
                found = filter(lambda c: c.name == n, self.classes)
                if len(found) > 0:
                    i.parent_images.append(found[0])
                else:
                    i.parent_images.append(None)

        print "Defined images:"
        for i in self.classes:
            print i

        self.load_macros()

    def make_plan(self, parsed):
        self.action = parsed.action

        self.to_act = []
        if parsed.name == None:
            for c in self.classes:
                for v in c.versions:
                    self.to_act.append((c, v))
        else:
            name = parsed.name
            if not "/" in parsed.name and not name.startswith(self.prefix) and self.prefix != "":
                name = self.prefix + name
                print "WARN Replace name %s with %s when prefix is defined" % (parsed.name, name)
            if parsed.version == None:
                filtered = filter(lambda c: c.name == name, self.classes)
                if len(filtered) > 0:
                    for v in filtered[0].versions:
                        self.to_act.append((filtered[0], v))
                else:
                    raise RuntimeError("Image named %s not found" % name)
            else:
                filtered = filter(lambda c: c.name == name and len(filter(lambda v: v == parsed.version, c.versions)) > 0, self.classes)
                if len(filtered) > 0:
                    self.to_act.append((filtered[0], parsed.version))
                else:
                    raise RuntimeError("Image named %s version %s not found" % (name, parsed.version))

        self.docker.cache_images()

    def take_action(self):
        if self.action == "generate":
            self.generate_dockerfiles()
        elif self.action == "build":
            self.generate_dockerfiles()
            self.build_images()
        elif self.action == "push":
            self.generate_dockerfiles()
            self.build_images()
            self.push_images()

    def generate_dockerfiles(self):
        if os.path.isdir(Project.build_dir):
            shutil.rmtree(Project.build_dir)

        os.mkdir(Project.build_dir)

        bad_cvs = []
        for cv in self.to_act:
            c = cv[0]
            v = cv[1]
            try:
                self.generate_dockerfile(c, v)
            except RuntimeError as e:
                bad_cvs.append(cv)
                print "WARN Ignored generating Dockerfile for %s:%s due to " \
                "one or more of its parent versions not found in mappings: %s" % \
                (c.name, v, e)
        for cv in bad_cvs:
            self.to_act.remove(cv)

    def generate_dockerfile(self, c, v):
        class_dir = Project.build_dir + "/" + os.path.basename(c.name)
        if not os.path.isdir(class_dir):
            os.mkdir(class_dir)

        version_dir = class_dir + "/" + v
        if not os.path.isdir(version_dir):
            os.mkdir(version_dir)
            if c.mappings.has_key(v):
                parent_name = c.mappings[v][0]
                parent_version = c.mappings[v][1]
                parent_index = c.parents.index(parent_name) # parent_name must be in parents because of mappings parsing
                parent_image = c.parent_images[parent_index]
                if c.parent_images[parent_index] != None:
                    self.generate_dockerfile(parent_image, parent_version)
                rendered = c.template.render(name=c.name, version=v, parent=parent_name, parent_version=parent_version)
            else:
                rendered = None
                shutil.rmtree(version_dir)
                raise RuntimeError("Image %s's mappings do not contain version %s" % (c.name, v))

            if rendered != None:
                with io.open(version_dir + "/Dockerfile", "w", encoding='utf8') as dockerfile:
                    dockerfile.write(rendered)
                for f in c.files:
                    shutil.copy2(f, version_dir)

    def build_images(self):
        self.docker.cache_images()

        for cv in self.to_act:
            c = cv[0]
            v = cv[1]
            try:
                self.build_image(c, v)
            except RuntimeError as e:
                print "WARN Failed to build image %s version %s due to %s" % \
                (c.name, v, e)

    def build_image(self, c, v):
        if c.mappings.has_key(v):
            parent_name = c.mappings[v][0]
            parent_version = c.mappings[v][1]
            parent_index = c.parents.index(parent_name) # parent_name must be in parents because of mappings parsing
            parent_image = c.parent_images[parent_index]
            if parent_image != None and not self.docker.cached_image(parent_name, parent_version):
                self.build_image(parent_image, parent_version)
        else:
            raise RuntimeError("Image %s's mappings do not contain version %s" % (c.name, v))

        print "INFO Build image %s:%s ..." % (c.name, v)
        path = Project.build_dir + "/" + os.path.basename(c.name) + "/" + v
        self.docker.build_image(c.name, v, path)

    def push_images(self):
        for cv in self.to_act:
            c = cv[0]
            v = cv[1]
            try:
                self.push_image(c, v)
            except RuntimeError as e:
                print "WARN Failed to push image %s version %s due to %s" % \
                (c.name, v, e)

    def push_image(self, c, v):
        print "INFO Push image %s:%s ..." % (c.name, v)
        self.docker.push_image(c.name, v)

if __name__ == "__main__":
    """
    python dib.py [operation] [options]
    operation:
        generate [-n <name>] [-v <version>]
        build [-n <name>] [-v <version>]
        push [-n <name>] [-v <version>]
        clean [-n <name>] [-v <version>]
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='actions', dest="action")
    parser_subs = []
    parser_subs.append(subparsers.add_parser('generate', help='generate Dockerfiles based on templates'))
    parser_subs.append(subparsers.add_parser('build', help='build images on generated Dockerfiles'))
    parser_subs.append(subparsers.add_parser('push', help='push built images'))
    parser_subs.append(subparsers.add_parser('clean', help='clean build directory'))
    for sub in parser_subs:
        sub.add_argument('-n', '--name', help='image name')
        sub.add_argument('-v', '--version', help='image version')
    parsed = parser.parse_args()

    project = Project()
    try:
        project.load_image_definition()
        project.make_plan(parsed)
        project.take_action()
    except RuntimeError as e:
        print "ERROR %s" % e
