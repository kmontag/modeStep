# Manages configuration for this repository.

variable "github_owner" {
  default = "kmontag"
}

variable "github_repository_name" {
  default = "modeStep"
}

provider "github" {
  # Owner for e.g. repository resources.
  owner = var.github_owner
}

resource "github_repository" "default" {
  name       = var.github_repository_name
  visibility = "public"

  description = "Ableton Live 12 control surface for the SoftStep 2"

  vulnerability_alerts = true

  # Suggest updating PR branches.
  allow_update_branch = true

  # Don't allow merge commits from PRs (they should be squashed or rebased instead).
  allow_merge_commit = false

  # Allow squash merges and use the PR body as the default commit content.
  allow_squash_merge          = true
  squash_merge_commit_title   = "PR_TITLE"
  squash_merge_commit_message = "PR_BODY"

  # Clean up branches after merge.
  delete_branch_on_merge = true

  has_downloads = true
  has_issues    = true
  has_projects  = false
  has_wiki      = false
}

import {
  to = github_repository.default
  id = var.github_repository_name
}
