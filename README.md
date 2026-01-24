# Ploston Runner

Local runner for Ploston - executes workflows on your machine with access to local MCPs (filesystem, docker, git, shell).

## Installation

```bash
pip install ploston-runner
```

## Usage

```bash
# Connect to Control Plane
ploston-runner connect --token <your-token> --cp-url wss://cp.example.com/runner --name my-laptop

# Or use environment variables
export PLOSTON_RUNNER_TOKEN=your-token
export PLOSTON_CP_URL=wss://cp.example.com/runner
export PLOSTON_RUNNER_NAME=my-laptop
ploston-runner connect
```

## Configuration

Create a config file `~/.ploston/runner.yaml`:

```yaml
control_plane: "wss://cp.example.com/runner"
auth_token: "ploston_runner_xxxxx"
runner_name: "my-laptop"
```

## License

Apache-2.0
