variable "GIT_SHA" {
  default = "local"
}

variable "IMAGE_REGISTRY" {
  default = "xju-oj"
}

variable "CACHE_REGISTRY" {
  default = ""
}

variable "BUILD_VERSION" {
  default = "phase1"
}

variable "BUILD_CREATED" {
  default = "unknown"
}

variable "BUILD_NETWORK" {
  default = "default"
}

variable "FRONTEND_BASE_IMAGE" {
  default = "xju-oj-frontend-base:node-24.19.0-bookworm-slim-v1"
}

variable "PNPM_VERSION" {
  default = "11.22.0"
}

# Debian mirror for the backend image; deploy.sh picks the in-region one on Huawei Cloud.
variable "DEBIAN_MIRROR" {
  default = "https://repo.huaweicloud.com"
}

group "default" {
  targets = ["postgres", "frontend", "backend", "judge-toolchain", "server"]
}

target "_common" {
  platforms = ["linux/amd64"]
  args = {
    GIT_COMMIT    = "${GIT_SHA}"
    VCS_REF      = "${GIT_SHA}"
    BUILD_VERSION = "${BUILD_VERSION}"
  }
  labels = {
    "org.opencontainers.image.source"   = "xju-OJ"
    "org.opencontainers.image.revision" = "${GIT_SHA}"
    "org.opencontainers.image.version"  = "${BUILD_VERSION}"
    "org.opencontainers.image.created"  = "${BUILD_CREATED}"
  }
  network = "${BUILD_NETWORK}"
}

target "postgres" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "deploy/images/postgres/Dockerfile"
  tags       = ["${IMAGE_REGISTRY}/postgres:git-${GIT_SHA}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/postgres:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/postgres:buildcache,mode=max"] : []
}

target "frontend" {
  inherits   = ["_common"]
  context    = "./frontend"
  dockerfile = "Dockerfile"
  target     = "frontend-runtime"
  args       = {
    FRONTEND_BASE_IMAGE = "${FRONTEND_BASE_IMAGE}"
    PNPM_VERSION        = "${PNPM_VERSION}"
  }
  tags       = ["${IMAGE_REGISTRY}/frontend:git-${GIT_SHA}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/frontend:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/frontend:buildcache,mode=max"] : []
}

target "frontend-base" {
  inherits   = ["_common"]
  context    = "./frontend"
  dockerfile = "Dockerfile"
  target     = "frontend-base"
  args       = {
    PNPM_VERSION = "${PNPM_VERSION}"
  }
  tags       = ["${FRONTEND_BASE_IMAGE}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/frontend-base:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/frontend-base:buildcache,mode=max"] : []
}

target "backend" {
  inherits   = ["_common"]
  context    = "./backend"
  dockerfile = "Dockerfile"
  target     = "backend-runtime"
  args       = {
    DEBIAN_MIRROR = "${DEBIAN_MIRROR}"
  }
  tags       = ["${IMAGE_REGISTRY}/backend:git-${GIT_SHA}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/backend:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/backend:buildcache,mode=max"] : []
}

target "judge-toolchain" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "server/Dockerfile"
  target     = "judge-toolchain"
  tags       = ["${IMAGE_REGISTRY}/judge-toolchain:tc-${GIT_SHA}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/judge-toolchain:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/judge-toolchain:buildcache,mode=max"] : []
}

target "server" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "server/Dockerfile"
  target     = "judge-server"
  tags       = ["${IMAGE_REGISTRY}/server:git-${GIT_SHA}"]
  cache-from = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/server:buildcache"] : []
  cache-to   = CACHE_REGISTRY != "" ? ["type=registry,ref=${CACHE_REGISTRY}/server:buildcache,mode=max"] : []
}
