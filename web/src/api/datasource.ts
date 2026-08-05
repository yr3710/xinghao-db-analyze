/**
 * 数据源相关 API 封装
 */
import { useUserStore } from '@/store/business/userStore'

/**
 * 获取数据源列表
 */
export async function fetch_datasource_list() {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/list`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 获取单个数据源详情
 */
export async function fetch_datasource_detail(id: number | string) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/get/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 删除数据源
 */
export async function delete_datasource(id: number | string) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/delete/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 检查数据源连接
 */
export async function check_datasource_connection(data: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/check`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  })
  return fetch(req)
}

/**
 * 新增数据源
 */
export async function add_datasource(data: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/add`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  })
  return fetch(req)
}

/**
 * 更新数据源
 */
export async function update_datasource(data: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/update`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  })
  return fetch(req)
}

/**
 * 获取已授权用户
 */
export async function get_authorized_users(datasourceId: number) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/getAuthorizedUsers/${datasourceId}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  return fetch(req)
}

/**
 * 数据源授权
 */
export async function authorize_datasource(datasourceId: number, userIds: number[]) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/authorize`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      datasource_id: datasourceId,
      user_ids: userIds,
    }),
  })
  return fetch(req)
}

export async function fetch_datasource_table_list(dsId: number | string) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/tableList/${dsId}`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: { Authorization: `Bearer ${token}` },
  }))
}

export async function fetch_datasource_field_list(tableId: number | string) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/fieldList/${tableId}`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: { Authorization: `Bearer ${token}` },
  }))
}

export async function fetch_tables_by_conf(data: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/getTablesByConf`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  }))
}

export async function fetch_fields_by_conf(data: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/getFieldsByConf`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  }))
}

export async function sync_datasource_tables(
  dsId: number | string,
  tables: any[],
  isSelectAll = false,
) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/syncTables/${dsId}`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ tables, is_select_all: isSelectAll }),
  }))
}

export async function save_datasource_table(tableData: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/saveTable`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(tableData),
  }))
}

export async function save_datasource_field(fieldData: any) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  const url = new URL(`${location.origin}/sanic/datasource/saveField`)
  return fetch(new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(fieldData),
  }))
}
