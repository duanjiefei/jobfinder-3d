# -*- coding: utf-8 -*-
"""抓取适配器注册表。"""
from .company_official import CompanyOfficialAdapter
from .nowcoder import NowcoderAdapter
from .tencent import TencentAdapter

ADAPTERS = {
    "official": CompanyOfficialAdapter,
    "tencent": TencentAdapter,
    "nowcoder": NowcoderAdapter,
}
