package main

deny contains msg if {
	r := input.resource_changes[_]
	r.type == "google_storage_bucket"
	not r.change.after.labels.environment
	msg := sprintf("Resource %s is missing the 'environment' label.", [r.address])
}

deny contains msg if {
	r := input.resource_changes[_]
	r.type == "google_storage_bucket"
	r.change.after.labels.environment
	r.change.after.labels.environment != "capstone"
	msg := sprintf(
		"Resource %s has environment='%s', expected 'capstone'.",
		[r.address, r.change.after.labels.environment]
	)
}
