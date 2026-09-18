"""Entry point: python run.py [--init-db]"""
import argparse

from rmtask.config import load_env, env
from rmtask.storage.db import DB
from rmtask.web.app import create_app

load_env()


def main() -> None:
    parser = argparse.ArgumentParser(description="RoboMaster Research Task & Info Hub")
    parser.add_argument("--init-db", action="store_true", help="recreate the local database")
    args = parser.parse_args()

    DB(env.db_path).init(force=args.init_db)
    app = create_app()
    app.run(host=env.host, port=env.port, debug=env.debug)


if __name__ == "__main__":
    main()
