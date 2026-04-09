# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

FROM python:3.10-slim

# 1. Create a non-root user with UID 1000 to match your host user
RUN useradd -m -u 1000 spoolman

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

# Python and S2S native environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DIR=/configs
ENV SLICER=prusaslicer
ENV URL=http://spoolman.local:7912
ENV UPDATES=true
ENV DELETE_ALL=false
ENV VERBOSE=false

# 6. Launch the service
# The application now natively reads the environment variables defined above
ENTRYPOINT [ "spoolman2slicer" ]
