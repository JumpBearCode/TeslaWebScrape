# Tesla Inventory Data Dictionary

Slim fields extracted from Tesla v4 inventory API (123 raw fields → 27 slim fields).

## Vehicle Identity

| Field | Type | Description |
|-------|------|-------------|
| `VIN` | string | 车辆识别码 |
| `Year` | int | 年份 |
| `Model` | string | 车型代码 (my=Model Y, m3=Model 3) |
| `TrimName` | string | 具体配置名称 |

## Pricing

| Field | Type | Description |
|-------|------|-------------|
| `TotalPrice` | int | 总价 ($) |
| `PriceAdjustmentUsed` | int | 价格调整/降价金额 ($) |
| `TransportationFee` | int | 运输费 ($) |

## Mileage & Battery

| Field | Type | Description |
|-------|------|-------------|
| `Odometer` | int | 里程 (mi) |
| `ActualRange` | int | 当前实际续航 (mi) — 电池健康指标 |

## Appearance

| Field | Type | Description |
|-------|------|-------------|
| `PAINT` | list[str] | 车身颜色 |
| `INTERIOR` | list[str] | 内饰颜色 |
| `WHEELS` | list[str] | 轮毂尺寸 |

## Location

| Field | Type | Description |
|-------|------|-------------|
| `City` | string | 所在城市 |
| `StateProvince` | string | 所在州 |

## Timeline

| Field | Type | Description |
|-------|------|-------------|
| `FactoryGatedDate` | datetime | 出厂日期 |
| `FirstRegistrationDate` | datetime | 首次注册日期 |

## Vehicle History & Condition

| Field | Type | Description |
|-------|------|-------------|
| `VehicleHistory` | string | 车辆历史 (CLEAN / PREVIOUS ACCIDENT(S)) |
| `DamageDisclosure` | bool | 损伤披露 |
| `DamageDisclosureStatus` | string | 损伤披露状态 |
| `CPORefurbishmentStatus` | string | 官方认证翻新状态 |

## Provenance

| Field | Type | Description |
|-------|------|-------------|
| `AcquisitionSubType` | string | 来源 (NONE=个人, PARTNER_LEASING=租赁回收) |
| `FleetVehicle` | bool | 是否车队车 |
| `IsDemo` | bool | 是否展示车 |
| `VehicleSubType` | string | 车辆子类型 (On-Site Ready / Used Test-drive) |
| `TitleSubtype` | string | 产权类型 (FIRSTREG=一手车) |

## Features & Media

| Field | Type | Description |
|-------|------|-------------|
| `AUTOPILOT` | list[str] | 自动驾驶配置 |
| `HasVehiclePhotos` | bool | 是否有实车照片 |
