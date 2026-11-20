"""The drift scenarios. Each one copies a change people make outside Terraform.

inject(ctx) makes the change with doctl and returns a dict of facts to record.
Resources created outside Terraform are written to .lab/outside.json so that
cleanup_outside.py (and teardown.sh) can delete them.
"""
import json

from common import LAB, ZONE, doctl, state

OUTSIDE = LAB / "outside.json"


def remember(kind, rid, name):
    items = json.loads(OUTSIDE.read_text()) if OUTSIDE.exists() else []
    items.append({"type": kind, "id": str(rid), "name": name})
    OUTSIDE.write_text(json.dumps(items, indent=2))


def ctx():
    """IDs of the managed resources, read from the state."""
    c = {}
    for r in state():
        v = r["values"]
        if r["address"] == "digitalocean_droplet.web":
            c["droplet"] = str(v["id"])
        elif r["address"] == "digitalocean_firewall.web":
            c["firewall"] = v["id"]
        elif r["address"] == "digitalocean_ssh_key.lab":
            c["fingerprint"] = v["fingerprint"]
        elif r["address"].startswith("digitalocean_record."):
            c["record_" + r["name"]] = str(v["id"])
    return c


def droplet_create(name, tags):
    args = ["compute", "droplet", "create", name, "--region", "lon1", "--size", "s-1vcpu-512mb-10gb",
            "--image", "ubuntu-24-04-x64", "--ssh-keys", ctx()["fingerprint"], "--wait"]
    if tags:
        args += ["--tag-names", ",".join(tags)]
    d = doctl(*args)[0]
    remember("droplet", d["id"], name)
    return {"created": f"droplet {d['id']}"}


def s_firewall_rule_added(c):
    # Console edit during an incident: open SSH to the world "for five minutes".
    doctl("compute", "firewall", "add-rules", c["firewall"],
          "--inbound-rules", "protocol:tcp,ports:22,address:0.0.0.0/0,address:::/0")
    return {}


def s_dns_hotfix(c):
    # Emergency failover: point app at a standby IP and drop the TTL.
    doctl("compute", "domain", "records", "update", ZONE, "--record-id", c["record_app"],
          "--record-data", "198.51.100.7", "--record-ttl", "60")
    return {}


def s_tag_removed(c):
    # A tag cleanup removes dl-web from the droplet. The firewall targets that tag.
    doctl("compute", "droplet", "untag", c["droplet"], "--tag-name", "dl-web")
    return {}


def s_tag_added(c):
    # Someone tags the droplet by hand (the console creates the tag on the fly).
    doctl("compute", "tag", "create", "dl-owner-oncall")
    doctl("compute", "droplet", "tag", c["droplet"], "--tag-name", "dl-owner-oncall")
    remember("tag", "dl-owner-oncall", "dl-owner-oncall")
    return {}


def s_record_deleted(c):
    # "Unused" TXT record deleted during a DNS cleanup.
    doctl("compute", "domain", "records", "delete", ZONE, c["record_verify"], "--force")
    return {}


def s_record_created(c):
    # A debug record added by hand in the managed zone.
    r = doctl("compute", "domain", "records", "create", ZONE, "--record-type", "A",
              "--record-name", "debug", "--record-data", "198.51.100.8", "--record-ttl", "60")[0]
    remember("record", r["id"], "debug")
    return {"created": f"record {r['id']}"}


def s_firewall_created(c):
    # A second firewall, made by hand, opens 8080 on the web droplet.
    fw = doctl("compute", "firewall", "create", "--name", "dl-hotfix-8080",
               "--inbound-rules", "protocol:tcp,ports:8080,address:0.0.0.0/0,address:::/0",
               "--droplet-ids", c["droplet"])[0]
    remember("firewall", fw["id"], "dl-hotfix-8080")
    return {"created": f"firewall {fw['id']}"}


def s_droplet_created_tagged(c):
    # A debug copy of the web server, made by hand with the same tag.
    return droplet_create("dl-web-debug", ["dl-web"])


def s_droplet_created_untagged(c):
    # A scratch droplet made by hand, no tags, default project.
    return droplet_create("dl-scratch-1", [])


def s_backups_enabled(c):
    # Someone turns on backups in the console.
    doctl("compute", "droplet-action", "enable-backups", c["droplet"], "--wait")
    return {}


def s_project_moved(c):
    # The droplet is moved to the default project in the console.
    default = doctl("projects", "get", "default")[0]["id"]
    doctl("projects", "resources", "assign", default, "--resource", f"do:droplet:{c['droplet']}")
    return {}


def s_firewall_deleted(c):
    # The managed firewall is deleted by hand.
    doctl("compute", "firewall", "delete", c["firewall"], "--force")
    return {}


SCENARIOS = {
    "firewall-rule-added": s_firewall_rule_added,
    "dns-hotfix": s_dns_hotfix,
    "tag-removed": s_tag_removed,
    "tag-added": s_tag_added,
    "record-deleted": s_record_deleted,
    "record-created": s_record_created,
    "firewall-created": s_firewall_created,
    "droplet-created-tagged": s_droplet_created_tagged,
    "droplet-created-untagged": s_droplet_created_untagged,
    "backups-enabled": s_backups_enabled,
    "project-moved": s_project_moved,
    "firewall-deleted": s_firewall_deleted,
}
