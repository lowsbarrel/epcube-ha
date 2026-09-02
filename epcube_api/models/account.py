"""Account-level models."""

from __future__ import annotations

from .base import ApiBool, ApiDateTime, ApiInt, ApiStr, EpCubeModel


class Account(EpCubeModel):
    """`user/user/base` - the signed-in user.

    `def_dev_sg_sn` is the plant serial the rest of the API is keyed on, so this
    endpoint is usually the first call of a session.
    """

    def_dev_sg_sn: ApiStr = None
    """Default plant serial. Feeds `homeDeviceInfo(sn=...)`."""
    user_id: ApiStr = None
    user_name: ApiStr = None
    nick_name: ApiStr = None
    email: ApiStr = None
    phone: ApiStr = None
    avatar: ApiStr = None
    language: ApiStr = None
    country: ApiStr = None
    time_zone: ApiStr = None
    user_type: ApiStr = None
    def_dev_id: ApiStr = None
    """Numeric device id of the default plant - saves a homeDeviceInfo call
    when only the id is needed."""
    def_dev_name: ApiStr = None
    def_dev_type: ApiInt = None
    correct_email: ApiStr = None
    grid_standard: ApiInt = None
    triphase_authority: ApiInt = None
    parallel_install: ApiInt = None
    update_time: ApiDateTime = None
    is_install_user: ApiBool = None
    create_time: ApiDateTime = None
    device_num: ApiInt = None


class LoginResult(EpCubeModel):
    """`open/common/login` - what a successful sign-in returns."""

    token: ApiStr = None
    user_id: ApiStr = None
    expire_time: ApiDateTime = None
