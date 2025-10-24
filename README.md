# Prebunking at scale

## Introduction

This is a monorepo for the prebunking-at-scale project, consisting of the infrastructure,
deployment tooling and application code. It is a work-in-progress and do expect process
and code changes as we refine the approach over the coming weeks.

## Getting started

### Installation

To install the repository just run:

`uv sync --all-packages`

from the repository root.

### Deployment

To deploy a project currently requires a few steps:

* Write a Containerfile (Dockerfile) for the project in it's directory under `projects/src/`
* Add the project to `compose.yaml`
* Build the image for the project with the name you added to the compose file with `<podman, docker> compose build <project>`
* Push the built image with `<podman, docker> push europe-west4-docker.pkg.dev/pas-shared/pas/<project>:<tag>` *make sure the tag is correct!*
* Write a Kubernetes manifest for the project under `deployments/`
* Apply that manifest with `kubectl apply -f <manifest>`

So for example to deploy `tubescraper` to production:

```
$ gcloud container clusters get-credentials prod-cluster --project pas-production-1 --location europe-west4-b
$ DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build tubescraper
$ docker push europe-west4-docker.pkg.dev/pas-shared/pas/tubescraper:latest
$ kubectl apply -f deployments/tubescraper.prod.yml # optional, only if you've changed it
```

## TODO

- [] Installation
- [] Initialising a library
- [] Initialising an application
- [] Testing
- [] Kubernetes stuff
- [] Terraform
