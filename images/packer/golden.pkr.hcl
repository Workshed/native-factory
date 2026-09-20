# Native Factory golden image.
#
# Layers the factory toolchain over the cirruslabs macOS+Xcode base image. A project run
# clones this rather than reinstalling dependencies (the brief).
#
# NOTE: the packer-plugin-tart block below follows the documented schema but has not been
# run on this host yet. The first `native-factory vm create` is the verification; adjust
# here if the plugin rejects an argument, and record what changed in docs/vm.md.

packer {
  required_plugins {
    tart = {
      version = ">= 1.12.0"
      source  = "github.com/cirruslabs/tart"
    }
  }
}

variable "base_image" {
  type        = string
  description = "Base image, ideally pinned by digest. Tags lie (see images/versions.lock.json)."
}

variable "image_name" {
  type        = string
  default     = "nf-golden"
  description = "Name of the resulting local Tart image."
}

variable "cpu_count" {
  type    = number
  default = 8
}

variable "memory_gb" {
  type    = number
  default = 16
}

variable "disk_size_gb" {
  type        = number
  default     = 160
  description = "The base Xcode image is ~140 GB uncompressed; leave room for the layer."
}

variable "template_sha256" {
  type        = string
  default     = "unset"
  description = "Hash of this template and its scripts, recorded in the image manifest."
}

variable "maestro_version" {
  type    = string
  default = "2.10.0"
}

variable "playwright_version" {
  type    = string
  default = "1.63.0"
}

variable "xcodebuildmcp_version" {
  type    = string
  default = "2.7.0"
}

variable "python_version" {
  type    = string
  default = "3.12"
}

source "tart-cli" "golden" {
  vm_base_name = var.base_image
  vm_name      = var.image_name
  cpu_count    = var.cpu_count
  memory_gb    = var.memory_gb
  disk_size_gb = var.disk_size_gb

  # Credentials of the official images.
  ssh_username = "admin"
  ssh_password = "admin"
  ssh_timeout  = "300s"

  # Build without a window. This is the Packer option; `tart run` has no --headless flag.
  headless = true
}

build {
  name    = "native-factory-golden"
  sources = ["source.tart-cli.golden"]

  # The factory's own Python packages, installed into the guest venv by 95-factory-runtime.
  provisioner "file" {
    source      = "${path.root}/../../packages"
    destination = "/tmp/native-factory-packages"
  }

  provisioner "file" {
    source      = "${path.root}/../versions.lock.json"
    destination = "/tmp/versions.lock.json"
  }

  provisioner "shell" {
    environment_vars = [
      "NF_PYTHON_VERSION=${var.python_version}",
      "NF_MAESTRO_VERSION=${var.maestro_version}",
      "NF_PLAYWRIGHT_VERSION=${var.playwright_version}",
      "NF_XCODEBUILDMCP_VERSION=${var.xcodebuildmcp_version}",
      "NF_BASE_IMAGE=${var.base_image}",
      "NF_TEMPLATE_SHA256=${var.template_sha256}",
    ]
    scripts = [
      "${path.root}/scripts/00-prepare.sh",
      "${path.root}/scripts/10-uv-python.sh",
      "${path.root}/scripts/20-node-tools.sh",
      "${path.root}/scripts/30-playwright.sh",
      "${path.root}/scripts/40-maestro.sh",
      "${path.root}/scripts/50-agent-device.sh",
      "${path.root}/scripts/60-xcodebuildmcp.sh",
      "${path.root}/scripts/70-openhands.sh",
      "${path.root}/scripts/80-acp-adapters.sh",
      "${path.root}/scripts/90-android-cli.sh",
      "${path.root}/scripts/95-factory-runtime.sh",
      "${path.root}/scripts/99-manifest.sh",
    ]
  }
}
