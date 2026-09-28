import argparse
import json
from pathlib import Path
from .generate import generate
from .simulator import Simulator, serve, APIError


def main():
    parser=argparse.ArgumentParser(prog='chronicle-forge')
    sub=parser.add_subparsers(dest='command',required=True)
    gen=sub.add_parser('generate');gen.add_argument('destination');gen.add_argument('--seed',type=int,default=42)
    server=sub.add_parser('serve');server.add_argument('corpus');server.add_argument('--port',type=int,default=8765)
    snap=sub.add_parser('snapshot');snap.add_argument('corpus');snap.add_argument('--at',required=True)
    snap.add_argument('--role',choices=['public','member'],default='public')
    snap.add_argument('--kind');snap.add_argument('--first',type=int,default=100)
    args=parser.parse_args()
    try:
        if args.command=='generate':print(generate(args.destination,args.seed))
        elif args.command=='serve':serve(args.corpus,port=args.port)
        else:print(json.dumps(Simulator(args.corpus).page(args.at,kind=args.kind,first=args.first,role=args.role),indent=2))
    except (ValueError,APIError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
