from xft.render.clab import load_intent
from xft.drivers.docker import configure
from pathlib import Path
import argparse
import sys
import yaml
import asyncio



REPO = Path(__file__).resolve().parents[2]
INTENT = REPO / "intent" / "ospf.yaml"


ROUTER_OSPF = "router ospf"
OSPF_P2P = "ip ospf network point-point"




ospf_intent = load_intent(path = INTENT)
ospf_scopes = []
ospf_defaults = {}

'''
futures todo
verify quickly the yaml file and its data using regex
'''


def apply_ospf_defaults() -> dict[str: str]:
    '''
    responsibe for handling all the defaults in yaml file
    only extracts the default values, doesnot check with the router, driver is responsible for that
    '''
    if ospf_defaults['default']:
        for key, value in ospf_intent['default']:
            ospf_defaults[key] = value
    else:
        return {}

def list_ospf_scopes() -> dict:
    '''
    responsible for listing all the ospf scopes from ospf.yaml file
    '''
    ospf_obj = {}
    for router_info in ospf_intent['routers']:
        router_name = router_info['name']
        ospf_obj[router_name] = []
        interface_info = {}
        interface_area = router_info['area']
        for int in interface_area:
            interface_info["interface"] = int['interface']
            interface_info["interface_area"] = int['area']
            ospf_obj[router_name].append(interface_info)
    return ospf_obj


def build_ospf_cmd():
    '''
    builds the ospf commands using the scopes
    '''
    scopes = list_ospf_scopes()
    cmds = {}
    for router, interfaces in scopes.items():
        router_id = router
        cmds[router_id] = []
        cmd_lst = []
        for int_info in interfaces:

            cmd_lst.append(f'interface {int_info['interface']}')
            cmd_lst.append(f'ip ospf area {int_info['interface_area']}')
            cmds[router_id].append(cmd_lst)
            cmd_lst = []
    print(cmds)


def apply_ospf_cmd(cmds: dict) -> tuple[bool, dict]:
    '''
    applies the ospf commands to the particular router
    calls the docker driver, configure method to apply the particular command
    '''

    for router, commands in cmds.items():
        

