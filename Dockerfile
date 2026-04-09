# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

FROM python:3.10-slim

# Create a non-root user with a fixed UID (1000) for volume compatibility
RUN useradd -m -u 1000 spoolman

WORKDIR /app

# Copy the application source code
COPY . .

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# The script uses 'appdirs' to find templates in the user's home directory.
# We pre-seed the new user's home with the required templates.
RUN mkdir -p /home/spoolman/.config/spoolman2slicer && \
    cp -r ./spoolman2slicer/data/* /home/spoolman/.config/spoolman2slicer/ && \
    chown -R spoolman:spoolman /home/spoolman

# Create the mount point and ensure it is writable by the 'spoolman' user
RUN mkdir -p /configs && chown spoolman:spoolman /configs

# Switch to the non-root user
USER spoolman

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SLICER=prusaslicer
ENV SPOOLMAN_URL=https://spoolman.local:7912/

# Launch the service with the internal configs directory
ENTRYPOINT [ "sh", "-c", "spoolman2slicer -U -d /configs -s ${SLICER} -u ${SPOOLMAN_URL}" ]
