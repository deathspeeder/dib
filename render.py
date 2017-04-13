import sys
from jinja2 import Environment, FileSystemLoader

if __name__ == "__main__":
    env = Environment(loader=FileSystemLoader('images'))
    for arg in sys.argv[1:]:
        template = env.get_template(arg)
        output = template.render()
        print(arg)
        print(output)
