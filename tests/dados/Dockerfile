ARG BASE=python:alpine
FROM ${BASE} AS build
FROM ubuntu:noble
RUN apt-get update && apt-get install -y curl=7.81.0-1 git
ENV DB_PASSWORD=abc123
COPY --from=composer:latest /usr/bin/composer /usr/bin/composer
USER root
