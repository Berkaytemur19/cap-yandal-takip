from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Kullanici


@admin.register(Kullanici)
class KullaniciAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'rol', 'is_active')
    list_filter = ('rol', 'is_active')
    fieldsets = UserAdmin.fieldsets + (('Rol', {'fields': ('rol',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Rol', {'fields': ('rol',)}),)

    def has_delete_permission(self, request, obj=None):
        return False
