"""Keyed weather providers — 需要 API key 的数据源。

每个 provider 通过 register() 函数注册到 weather._PROVIDER_REGISTRY。
惰性导入：仅当对应环境变量存在时才加载。
"""
