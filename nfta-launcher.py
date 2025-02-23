#!/usr/bin/env python3
import argparse
import json
import subprocess
import os
import requests
import logging


def load_config(config_file_path=None, platform="local"):
    try:
        if not os.path.isfile(config_file_path):
            config_file_path = os.path.join(os.getcwd(), "config.json")

        if not config_file_path:
            config_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

        logging.info(f"Loading configuration file: {config_file_path}")
        with open(config_file_path, "r") as config_file:
            config_data = json.load(config_file)
            if not config_data:
                logging.error("Configuration file is empty")
                return None
            return config_data[platform]
    except FileNotFoundError:
        logging.error(f"Configuration file not found {config_file_path}")
        return None


def download_tw_agent(location):
    logging.info(f"Downloading tw-agent to {location}")
    agent_url = "https://github.com/seqeralabs/tower-agent/releases/latest/download/tw-agent-linux-x86_64"
    if not os.path.isdir(location):
        logging.info(f"Creating the directory: {location}")
        os.makedirs(location)

    agent_path = os.path.join(location, "tw-agent")

    try:
        response = requests.get(agent_url, stream=True)
        response.raise_for_status()
        with open(agent_path, "wb") as agent_file:
            for chunk in response.iter_content(chunk_size=8192):
                agent_file.write(chunk)
        os.chmod(agent_path, 0o755)
        print("tw-agent downloaded and set up successfully.")
    except requests.exceptions.RequestException as e:
        print("Error downloading tw-agent:", e)


def init_parser():
    parser = argparse.ArgumentParser(description="Nextflow tower Agent launcher")
    parser.add_argument("--platform", choices=["local", "gadi", "setonix", "slurm", "pbspro"], default="local",
                        help="Platform for execution")
    parser.add_argument("--connection-id", type=str, help="Connection ID", dest="connection-id")
    parser.add_argument("--work-dir", type=str, help="Working directory", dest="work-dir")
    parser.add_argument("--access-token", type=str, help="Access token", dest="access-token")
    parser.add_argument("--config", type=str, help="configuration file", default=None)
    parser.add_argument("--update-agent", action="store_true", help="Update tw-agent", default=False, dest="update-agent")
    parser.add_argument("--user", type=str, help="User")
    parser.add_argument("--project", type=str, help="Project")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        dest="log-level", default="INFO", help="Logger level")
    parser.add_argument("--log-destination", dest="log_destination", choices=["stdout", "file"], default="stdout", help="Log destination")
    parser.add_argument("--agent-debug-mode", dest="agent-debug-mode", action="store_true", default=False, help="Enable agent debug mode")
    parser.add_argument("--agent-dir", dest="agent-dir", type=str, help="Agent directory")
    parser.add_argument("--hpc-job-conf", dest="hpc-job-conf", type=str,
                        help="Job configuration to overwrite default configuration")
    parser.add_argument("--job-log", dest="job-log",
                        help="path and prefix of output and error Log files for the submitted jobs")

    return parser


def submit_slurm_job(job_command, hpc_config, log_path=None):
    slurm_command = ["sbatch"]

    for key, value in hpc_config.items():
        # Check if the value is a string and enclose it in quotes
        if isinstance(value, str):
            slurm_command.extend(["--" + key, f"'{value}'"])
        else:
            slurm_command.extend(["--" + key, str(value)])

    if log_path:
        slurm_command.append(f"--output='{log_path}.out'")
        slurm_command.append(f"--error='{log_path}.err'")

    slurm_command.extend(["--wrap='" + job_command + "'"])

    logging.info(f"Slurm command:{' '.join(slurm_command)}")

    try:
        subprocess.run(" ".join(slurm_command), shell=True)

    except subprocess.CalledProcessError as e:
        print("Error submitting Slurm job:", e)


def submit_pbspro_job(job_command, hpc_config, log_dir):
    return


def submit_setonix_job(job_command, hpc_config, log_dir):
    # For Setonix, we'll use the logic for Slurm submission
    submit_slurm_job(job_command, hpc_config, log_dir)


def submit_gadi_job(job_command, hpc_config, log_dir):
    # For Gadi, we'll use the logic for Slurm submission
    submit_pbspro_job(job_command, hpc_config, log_dir)


def run_local_process(job_command, environment_variables={}):
    logging.info(f"Running: {' '.join(job_command)}")
    try:
        process = subprocess.Popen(job_command,
                                   env=environment_variables,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   universal_newlines=True)
        for line in process.stdout:
            print(line, end='')
        for line in process.stderr:
            print(line, end='')
        process.wait()
        if process.returncode != 0:
            logging.error(f"Local process exited with non-zero status: {process.returncode}")
            exit(1)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running local process: {e}")
        exit(1)


def update_config_from_args(config, args):
    for key, value in vars(args).items():
        if value is not None:
            config[key] = value


def validate_configurations(args):
    config = load_config(args.config, args.platform)
    update_config_from_args(config, args)
    if not config["access-token"] and "TOWER_ACCESS_TOKEN" in os.environ:
        args.access_token = os.environ["TOWER_ACCESS_TOKEN"]


    if not config["agent-dir"]:
        config["agent-dir"] = os.getcwd()

    if not config["user"]:
        config["user"] = os.environ.get("USER")

    if not config["work-dir"]:
        config["work-dir"] = "nfta-wdir"

    if not config["connection-id"]:
        connection_id = input("Please provide a connection ID: ")
        config["connection-id"] = connection_id

    if not config["access-token"]:
        access_token = input("Please provide an access token: ")
        config["access-token"] = access_token

    if not config["work-dir"] or not config["connection-id"] or not config["access-token"]:
        logging.error("Error: work-dir, connection-id, and access-token must be provided.")
        exit(1)

    if config["platform"] == "gadi":
        None

    elif config["platform"] == "setonix":
        if not config["project"]:
            config["project"] = os.environ.get("PAWSEY_PROJECT")

        if config["agent-dir"] and "{project}" in config["agent-dir"]:
            config["agent-dir"] = config["agent-dir"].format(project=config["project"])

        if config["work-dir"] and "{project}/{user}" in config["work-dir"]:
            config["work-dir"] = config["work-dir"].format(project=config["project"], user=config["user"])

        if config["project"]:
            config["job-config"]["account"] = config["project"]

    if not config["project"] or not config["user"]:
        logging.warning("We could not find the user name or the project code. "
                        "This can cause unexpected behaviure if you using them in any configuration!")
    return args, config


def build_agent_command(config):
    job_command = []
    custom_env = os.environ.copy()
    if config["agent-debug-mode"]:
        custom_env["LOGGER_LEVELS_IO_SEQERA_TOWER_AGENT"] = "TRACE"

    job_command.append(os.path.join(config["agent-dir"], "tw-agent"))
    job_command.append(config["connection-id"])
    job_command.extend(["-u", "https://tower.services.biocommons.org.au/api"])
    job_command.extend(["--work-dir", config["work-dir"]])
    job_command.extend(["--access-token", config["access-token"]])

    return job_command, custom_env


def configure_logging(log_level, log_destination):
    logging.basicConfig(level=log_level.upper())
    logger = logging.getLogger()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if log_destination.lower() == "stdout":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logging.info('Logging to stdout')
    elif log_destination:
        file_handler = logging.FileHandler(log_destination)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.info(f"Logging to file: {log_destination}")
    else:
        raise ValueError("Invalid log destination. Use 'stdout' or 'file'.")


def main():
    parser = init_parser()
    args = parser.parse_args()

    # Set up logging
    #configure_logging(config["log-level"], config["log-destination"])
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    args, config = validate_configurations(args)
    logging.info("Starting nfta-launcher application")
    logging.info(f"Tower agent directory: {config['agent-dir']}")
    logging.info(f"Agent work directory: {config['work-dir']}")
    logging.info(f"Execution mode: {config['platform']}")

    if config["update-agent"] or not os.path.exists(os.path.join(config["agent-dir"], "tw-agent")):
        download_tw_agent(config["agent-dir"])

    job_command, env_vars = build_agent_command(config)

    if not os.path.exists(config["work-dir"]):
        os.makedirs(config["work-dir"])
        logging.info(f"Created work directory for tower agent: {config['work-dir']}")

    if args.platform == "slurm":
        logging.error(f"Only local and setonix platforms are supported!")
        exit(1)
        #submit_slurm_job(job_command, config["job-config"], args.log_dir)
    elif args.platform == "pbspro":
        #submit_pbspro_job(job_command, args.hpc_config, args.log_dir)
        logging.error(f"Only local and setonix platforms are supported!")
        exit(1)
    elif args.platform == "gadi":
        #submit_gadi_job(job_command, args.hpc_config, args.log_dir)
        logging.error(f"Only local and setonix platforms are supported!")
        exit(1)
    elif args.platform.lower() == "setonix":
        job_command_str = " ".join(job_command)
        if config["agent-debug-mode"]:
            job_command_str = "LOGGER_LEVELS_IO_SEQERA_TOWER_AGENT=TRACE " + job_command_str
        submit_setonix_job(job_command_str, config["job-config"], config["job-log"])
    else:
        run_local_process(job_command, env_vars)


if __name__ == "__main__":
    main()
