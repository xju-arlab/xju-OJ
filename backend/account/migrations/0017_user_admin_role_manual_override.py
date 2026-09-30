from django.db import migrations, models


def preserve_existing_local_admins(apps, schema_editor):
    User = apps.get_model("account", "User")
    ExternalIdentity = apps.get_model("account", "ExternalIdentity")
    db = schema_editor.connection.alias
    for user in User.objects.using(db).exclude(admin_type="Regular User").iterator():
        identities = ExternalIdentity.objects.using(db).filter(user_id=user.pk).values_list("claims", flat=True)
        studio_admin = any(
            isinstance(claims, dict)
            and isinstance(claims.get("groups"), list)
            and "icthub-admins" in claims["groups"]
            for claims in identities
        )
        if not studio_admin:
            User.objects.using(db).filter(pk=user.pk).update(admin_role_manual_override=True)


class Migration(migrations.Migration):
    dependencies = [("account", "0016_userprofile_student_id")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="admin_role_manual_override",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(preserve_existing_local_admins, migrations.RunPython.noop),
    ]
