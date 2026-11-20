# Sources

Excerpts from the docs and source code the write-up relies on, as read on 2026-11-20.

## Terraform

[terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), `-detailed-exitcode`:

> 0 = Succeeded with empty diff (no changes)
> 1 = Error
> 2 = Succeeded with non-empty diff (changes present)

Refresh-only mode "creates a plan whose goal is only to update the Terraform state and any root module output values" to match "changes made to remote objects outside of Terraform".

[Generating configuration](https://developer.hashicorp.com/terraform/language/import/generating-configuration):

> Experimental: Configuration generation is available in Terraform v1.5 as an experimental feature.

> For certain resources with complex schemas, Terraform may not be able to construct a valid configuration from these values.

## OpenTofu

[Generating configuration](https://opentofu.org/docs/language/import/generating-configuration/):

> Configuration generation is available in OpenTofu v1.6 as an experimental feature.

## DigitalOcean

[API description, "Rate Limit"](https://github.com/digitalocean/openapi/blob/248d3a236d567820d335293e1cf4ce2ec87c52fa/specification/description.yml) (commit 248d3a2):

> Requests through the API are rate limited per OAuth token. Current rate limits:
> * 5,000 requests per hour
> * 250 requests per minute (5% of the hourly total)

[terraform-provider-digitalocean v2.108.0, resource_droplet.go](https://github.com/digitalocean/terraform-provider-digitalocean/blob/v2.108.0/digitalocean/droplet/resource_droplet.go), in the read function. The plan's view of `backups` comes from the droplet's `features` list:

```go
if features := droplet.Features; features != nil {
    d.Set("backups", slices.Contains(features, "backups"))
```

## driftctl and terraformer

[snyk/driftctl README](https://github.com/snyk/driftctl): "This project is now in maintenance mode. We cannot promise to review contributions." Cloud providers: "AWS, GitHub, Azure, GCP." Latest release [v0.40.0](https://github.com/snyk/driftctl/releases/tag/v0.40.0), 2023-12-01. The repository is not archived.

[driftctl v0.17.0 release notes](https://github.com/snyk/driftctl/releases/tag/v0.17.0): "Display out of sync drifts only in deep mode (#1235)".

[GoogleCloudPlatform/terraformer README](https://github.com/GoogleCloudPlatform/terraformer): "As of March 16, 2026, this repository has been archived." Its provider list includes DigitalOcean.
