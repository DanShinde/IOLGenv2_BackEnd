"""The tools shown on the hub page. Adding a tool is one entry here plus its view,
url and template -- the hub needs no edit of its own.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    slug: str
    name: str
    description: str
    icon: str        # a bootstrap-icons class, e.g. 'bi-card-text'
    url_name: str    # resolved in the template with {% url tool.url_name %}


TOOLS = [
    Tool(
        slug='text-list',
        name='IO Text List Generator',
        description='Turn an IO list into per-channel text lists for label and ferrule '
                    'printing -- tags, addresses, ferrules or a combination.',
        icon='bi-card-text',
        url_name='tools_textlist',
    ),
    Tool(
        slug='scl-io-mapping',
        name='SCL IO-Mapping Generator',
        description='Generate the TIA POKE_BLK block that maps the input, output and '
                    'HMI test data blocks for a given image size.',
        icon='bi-cpu',
        url_name='tools_scl',
    ),
]
