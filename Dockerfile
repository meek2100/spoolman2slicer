# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

FROM python:3.10-slim

# Make UID and GID configurable
ARG USER_UID=1000
ARG USER_GID=1000

# 1. Create a non-root user and group
RUN groupadd -g ${USER_GID} sm2s && \
    useradd -m -u ${USER_UID} -g sm2s sm2s

WORKDIR /app

# 2. Copy the source code and install the package
COPY . .
RUN pip install --no-cache-dir .

# 3. Pre-seed the configuration directory with templates
RUN mkdir -p /home/sm2s/.config/spoolman2slicer && \
    cp -r ./spoolman2slicer/data/* /home/sm2s/.config/spoolman2slicer/ && \
    chown -R sm2s:sm2s /home/sm2s

# 4. Set up the output volume mount point
RUN mkdir -p /configs && chown sm2s:sm2s /configs

# 5. Switch to the non-root user
USER sm2s

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
