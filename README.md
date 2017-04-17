# Introduction
dib (docker image build) is a build tool managing a group of docker images. dib tries to solve the following problems when building images:
* **Dependency management** Images generally have a long chain of parent dependency. In order to build the leaf image, its parent branch images must be ready or built.
* **Multiple inheritance** Docker image does not allow inherit from multiple parents. However, different versions of one image may have different parents. The Dockerfile structure for all versions are usually similar to each other or the same with others.
* **DSL for Dockerfile generation** Some structure of Dockerfile are used at many times from different images. A macro is needed to avoid write same block several times.
* **Version management** If an image's version need to represent its dependency relationship, the version name can be complex. e.g. image "spark:1.6.3-open7-u16.04" represents spark image 1.6.3 inherited from openjdk 7 which is from ubuntu 16.04. To manage the version naming, a good mechanism is needed.
* **Fault tolerance** When building a group of images, one image failure should not block others who have no dependency to the failed one. Users can also re-try the failed image chain.

# Use Case
Suppose we are trying to build a Spark image which has several version on different OS with different JDK versions. The dependency hierarchy may look like

![Example](https://raw.githubusercontent.com/deathspeeder/dib/master/public/example.png)

In which, image Spark has three versions inherited from two types of JDK (OpenJDK and Oracle JDK) who has its own parent OS, Ubuntu and centos.

# DSL
dib uses [Jinja](http://jinja.pocoo.org) for composing templates. To define an image, a package file and a Dockerfile template must be created at a sub-directory of parent directory "images". For example, to define image OpenJDK image, a folder named "images/lang/java-open" is created and in this folder there're two jinja files: "Dockerfile.j2" and "package.j2". The folder name can be anything that is valid to OS while two jinja file names are fixed.

Directory "images" is the parent folder for all image definitions. Users can define custom macros at "images" directory. e.g. an exmpale macro file is defined at "images/macros.j2"
```jinja
{% set project = 'dib' %}
{% set hub = 'localhost:5000' %}
{% set prefix = hub + '/' + project + '/' %}
{% set suffix = '-0.1' %}
{% set proxy = '' %}
```
In which some global variables are defined. Users can also create custom macros or blocks according to [Jinja](http://jinja.pocoo.org/docs/2.9/templates/#macros).

The OpenJDK image's two definition files are
* **package.j2** defines the image's versions and dependency structure. In OpenJDK's definition, e.g.
```jinja
{% import 'macros.j2' as g -%}
name={{g.prefix}}java-open
versions=7-u14.04,7-u16.04
type=class
parents={{g.prefix}}base-ubuntu
mappings=[0]:[0]:14.04,[1]:[0]:16.04
```
In which a key-value dictionary is defined with the following keys:
  * *name*: the name of the image (e.g. "spark", "localhost:5000/dib/java-open"), **required**
  * *versions*: the versions to create on the image, comma separated, **required**
  * *type*: can be 'class' or 'trait' ('trait' is not implemented yet, see [TODO](#TODO-list)), **required**
  * *parents*: all parent image names, comma separated, **required**
  * *mappings*: version dependency mapping relationship definitions. Comma separated tokens. Each token is one mapping with three parts representing version to parent:parent_version mapping, that is "version"->"parent:parent_version". The version and parent parts can be names or indexes of *versions* or *parents*. e.g. in this OpenJDK example, mapping "[0]:[0]:14.04" is the same with "7-u14.04:[0]:14.04" and "7-u14.04:{{g.prefix}}base-ubuntu:14.04", all meaning a mapping from version "7-u14.04" to parent "{{g.prefix}}base-ubuntu" with parent version "14.04". This field is **required**

When an image's dependency is defined in "package.j2", the image's Dockerfile can be generated from its template "Dockerfile.j2". e.g.
* **Dockerfile.j2** defines template for all versions' Dockerfile of OpenJDK
```jinja
FROM {{parent}}:{{parent_version}}

RUN apt-get install -y openjdk-7-jdk

ENV JAVA_HOME /usr/lib/jvm/java-7-openjdk
ENV PATH ${PATH}:${JAVA_HOME}/bin
```

Here, variables {{version}}, {{parent}} and {{parent_version}} will be replaced with definitions in "mappings" according to the image version to build. Users can also do some control structure definitions from [Jinja](http://jinja.pocoo.org/docs/2.9/templates/#list-of-control-structures) in "Dockerfile.j2", e.g.
```jinja
{% if version == '1.6.3' %}
    do something with 1.6.3
{% elif version == '2.0.0' %}
    do something with 2.0.0
{% else %}
    do others
{% endif %}
```

# Usage
dib provides following commands for manage images
```
python dib.py [operation] [options]
  operation:
      generate [-n <name>] [-v <version>]
      build [-n <name>] [-v <version>] [-p]
      push [-n <name>] [-v <version>] [-p]
      clean [-n <name>] [-v <version>] [-p]
```
* **generate**: generate Dockerfile
* **build**: generate and build images
* **push**: generate build and push images
* **clean**: clean image build directory
Call `python dib.py -h` or `python dib.py [operation] -h` for help.

# TODO list
* Circle dependency check
* Add 'trait' type support
