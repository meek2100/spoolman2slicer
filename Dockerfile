# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

FROM python:3.10-slim

# Make UID and GID configurable
ARG USER_UID=1000
ARG USER_GID=1000

# 1. Create a non-root user and group
RUN groupadd -g ${USER_GID} spoolman && \
    useradd -m -u ${USER_UID} -g spoolman spoolman

WORKDIR /app

# 2. Copy the source code and install the package
COPY . .
RUN pip install --no-cache-dir .

# 3. Pre-seed the configuration directory with templates
RUN mkdir -p /home/spoolman/.config/spoolman2slicer && \
    cp -r ./spoolman2slicer/data/* /home/spoolman/.config/spoolman2slicer/ && \
    chown -R spoolman:spoolman /home/spoolman

# 4. Set up the output volume mount point
RUN mkdir -p /configs && chown spoolman:spoolman /configs

# 5. Switch to the non-root user
USER spoolman

# Python and SM2S environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV SM2S_SLICER_CONFIG_DIR=/configs
ENV SM2S_SLICER=prusaslicer
ENV SM2S_SPOOLMAN_URL=http://spoolman.local:7912
ENV SM2S_LIVE_SYNC=true
ENV SM2S_STARTUP_TIDY=false
ENV SM2S_VERBOSE_LOGGING=false
ENV SM2S_VARIANTS=""
ENV SM2S_CREATE_PER_SPOOL=""

# 6. Launch the service
ENTRYPOINT [ "spoolman2slicer" ]
